"""Bounded, single-turn support agent. HTTP and approval decisions live outside the graph."""

import asyncio
import logging
import operator
import re
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Literal, NotRequired, TypedDict
from uuid import UUID

import aiohttp
import httpx
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import ValidationError

from support_agent.agent.citations import validate_citations
from support_agent.agent.context import ContextError, prepare_context, validate_context_capacity
from support_agent.agent.prompt import SYSTEM_PROMPT
from support_agent.core.config import Settings
from support_agent.schemas.conversation import MessageData
from support_agent.schemas.knowledge import RetrievedChunk
from support_agent.tools.support import SearchResults, ToolError, ToolResult

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    customer_id: str
    conversation_id: str
    run_id: str
    steps: Annotated[int, operator.add]
    history: list[dict[str, Any]]
    current_message: str
    messages: list[BaseMessage]
    retrieved: list[dict[str, Any]]
    pending_calls: list[dict[str, Any]]
    call_index: int
    llm_calls: int
    tool_calls: int
    retrieval_calls: int
    consecutive_failures: int
    retries: int
    remaining_seconds: float
    active_deadline: float
    status: Literal["running", "completed", "failed"]
    answer: NotRequired[str]
    citations: NotRequired[list[dict[str, Any]]]
    error: NotRequired[str]
    approval_requested: NotRequired[bool]
    approval_payload: NotRequired[dict[str, Any]]
    reset_rejected: NotRequired[bool]


# The reset callback only prepares/returns an immutable backend payload. It must not execute it.
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[ToolResult[Any]]]
PrepareApproval = Callable[[float], Awaitable[dict[str, Any]]]
ResolveApproval = Callable[[dict[str, Any]], Awaitable[ToolResult[Any]]]


def _transient(exc: Exception) -> bool:
    if isinstance(
        exc,
        (TimeoutError, httpx.TimeoutException, httpx.NetworkError, aiohttp.ClientConnectionError),
    ):
        return True
    status = getattr(exc, "status", None) or getattr(
        getattr(exc, "response", None), "status_code", None
    )
    # NVIDIA's SDK currently raises plain Exception with a formatted status prefix.
    if status is None and type(exc) is Exception:
        match = re.match(r"^\[(\d{3})\]", str(exc))
        status = int(match.group(1)) if match else None
    return status == 429 or (isinstance(status, int) and 500 <= status < 600)


def _remaining(state: AgentState, started: float) -> float:
    now = time.monotonic()
    return max(
        0.0, min(state["remaining_seconds"] - (now - started), state["active_deadline"] - now)
    )


def _failure(code: str, message: str, retryable: bool = False) -> ToolResult[Any]:
    return ToolResult(
        success=False, error=ToolError(code=code, message=message, retryable=retryable)
    )


def _as_text(message: AIMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    return "\n".join(part.get("text", "") for part in message.content if isinstance(part, dict))


def build_graph(
    model: Any,
    execute_tool: ToolExecutor,
    prepare_approval: PrepareApproval,
    resolve_approval: ResolveApproval,
    settings: Settings,
    checkpointer: Any,
):
    """Build a graph with backend-bound tools and a caller-supplied durable checkpointer.

    `resolve_approval` must read a decision/result verified by the backend, not trust
    the value passed to LangGraph's resume command. No reset execution occurs here.
    """

    def prepare(state: AgentState) -> dict[str, Any]:
        history = [MessageData.model_validate(item) for item in state["history"]]
        return {
            "messages": prepare_context(
                history, state["current_message"], settings.history_token_budget
            )
        }

    async def call_model(state: AgentState) -> dict[str, Any]:
        started = time.monotonic()
        try:
            validate_context_capacity(state["messages"], settings.model_context_token_budget)
        except ContextError:
            return {"status": "failed", "error": "CONTEXT_LIMIT"}
        attempts = state["llm_calls"] + 1
        try:
            timeout = min(
                settings.llm_timeout_seconds,
                state["remaining_seconds"],
                max(0.0, state["active_deadline"] - time.monotonic()),
            )
            async with asyncio.timeout(timeout):
                response = await model.ainvoke(
                    [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
                )
            if not isinstance(response, AIMessage):
                raise TypeError("Model did not return an assistant message")
            remaining = _remaining(state, started)
            if remaining <= 0:
                return {
                    "llm_calls": attempts,
                    "remaining_seconds": 0,
                    "status": "failed",
                    "error": "DEADLINE_EXCEEDED",
                }
            calls = list(response.tool_calls)
            # Malformed tool calls are still attempts; represent them as rejected calls.
            calls.extend(
                {
                    "name": item.get("name") or "",
                    "args": {},
                    "id": item.get("id") or f"invalid-{index}",
                    "invalid": True,
                }
                for index, item in enumerate(response.invalid_tool_calls)
            )
            return {
                "messages": [*state["messages"], response],
                "pending_calls": calls,
                "call_index": 0,
                "llm_calls": attempts,
                "remaining_seconds": remaining,
                "retries": 0,
            }
        except Exception as exc:
            remaining = _remaining(state, started)
            retry = (
                _transient(exc)
                and state["retries"] < settings.max_provider_retries
                and attempts < settings.max_llm_calls
                and remaining > 0
            )
            logger.warning("agent_model_failed", extra={"retry": retry, "attempt": attempts})
            if retry:
                delay = min(0.25 * 2 ** state["retries"], remaining)
                await asyncio.sleep(delay)
                remaining = max(0.0, remaining - delay)
                if remaining > 0:
                    return {
                        "llm_calls": attempts,
                        "remaining_seconds": remaining,
                        "retries": state["retries"] + 1,
                    }
            return {
                "llm_calls": attempts,
                "remaining_seconds": remaining,
                "status": "failed",
                "error": "DEADLINE_EXCEEDED" if remaining <= 0 else "PROVIDER_UNAVAILABLE",
            }

    def route_model(state: AgentState) -> str:
        if state["status"] == "failed":
            return "finalize"
        if state["retries"]:
            return "model"
        if state["pending_calls"]:
            return "tools"
        return "finalize"

    async def tools(state: AgentState) -> dict[str, Any]:
        call = state["pending_calls"][state["call_index"]]
        name = call.get("name", "")
        attempted = state["tool_calls"] + 1
        retrievals = state["retrieval_calls"] + (name == "search_knowledge_base")
        started = time.monotonic()
        if attempted > settings.max_tool_calls or retrievals > settings.max_retrieval_calls:
            return {
                "status": "failed",
                "error": "EXECUTION_LIMIT",
                "tool_calls": attempted,
                "retrieval_calls": retrievals,
            }
        try:
            if call.get("invalid") or not isinstance(call.get("args"), dict):
                result = _failure("INVALID_TOOL_ARGUMENTS", "The tool input is invalid.")
            elif name == "request_password_reset" and state.get("reset_rejected"):
                result = _failure("ACTION_REJECTED", "The reset was rejected; do not repeat it.")
            else:
                budget = min(
                    state["remaining_seconds"],
                    max(0.0, state["active_deadline"] - time.monotonic()),
                )
                async with asyncio.timeout(budget):
                    result = await execute_tool(name, call["args"])
        except TimeoutError:
            return {
                "status": "failed",
                "error": "DEADLINE_EXCEEDED",
                "remaining_seconds": 0,
                "tool_calls": attempted,
                "retrieval_calls": retrievals,
            }
        except Exception:
            if (
                time.monotonic() >= state["active_deadline"]
                or time.monotonic() - started >= state["remaining_seconds"]
            ):
                return {
                    "status": "failed",
                    "error": "DEADLINE_EXCEEDED",
                    "remaining_seconds": 0,
                    "tool_calls": attempted,
                    "retrieval_calls": retrievals,
                }
            logger.exception("agent_tool_failed", extra={"tool": name})
            result = _failure("TOOL_UNAVAILABLE", "The requested operation is unavailable.")
        remaining = _remaining(state, started)
        if remaining <= 0:
            return {
                "status": "failed",
                "error": "DEADLINE_EXCEEDED",
                "remaining_seconds": 0,
                "tool_calls": attempted,
                "retrieval_calls": retrievals,
            }
        common = {
            "tool_calls": attempted,
            "retrieval_calls": retrievals,
            "remaining_seconds": remaining,
        }
        if name == "request_password_reset" and result.success:
            return {**common, "consecutive_failures": 0, "approval_requested": True}
        failures = 0 if result.success else state["consecutive_failures"] + 1
        retrieved = state["retrieved"]
        if name == "search_knowledge_base" and result.success:
            try:
                results = SearchResults.model_validate(result.data)
                retrieved = [
                    *retrieved,
                    *[chunk.model_dump(mode="json") for chunk in results.chunks],
                ]
            except (ValidationError, TypeError):
                result = _failure("INVALID_TOOL_RESULT", "Knowledge search is unavailable.")
                failures = state["consecutive_failures"] + 1
        update = {
            **common,
            "retrieved": retrieved,
            "consecutive_failures": failures,
            "messages": [
                *state["messages"],
                ToolMessage(content=result.model_dump_json(), tool_call_id=call["id"]),
            ],
            "call_index": state["call_index"] + 1,
        }
        if failures >= settings.max_consecutive_tool_failures:
            update.update(status="failed", error="TOOL_FAILURE_LIMIT")
        return update

    def route_tools(state: AgentState) -> str:
        if state["status"] == "failed":
            return "finalize"
        if state["consecutive_failures"] >= settings.max_consecutive_tool_failures:
            return "limit"
        if state.get("approval_requested"):
            return "prepare_approval"
        if state["call_index"] < len(state["pending_calls"]):
            return "tools"
        return "model" if state["llm_calls"] < settings.max_llm_calls else "limit"

    async def prepare_action(state: AgentState) -> dict[str, Any]:
        started = time.monotonic()
        try:
            budget = min(
                state["remaining_seconds"], max(0.0, state["active_deadline"] - time.monotonic())
            )
            async with asyncio.timeout(budget):
                payload = await prepare_approval(budget)
        except TimeoutError:
            return {"status": "failed", "error": "DEADLINE_EXCEEDED", "remaining_seconds": 0}
        except Exception as exc:
            if (
                time.monotonic() >= state["active_deadline"]
                or time.monotonic() - started >= state["remaining_seconds"]
                or getattr(getattr(exc, "orig", None), "sqlstate", None) == "57014"
            ):
                return {"status": "failed", "error": "DEADLINE_EXCEEDED", "remaining_seconds": 0}
            logger.exception("agent_approval_prepare_failed")
            return {"status": "failed", "error": "APPROVAL_UNAVAILABLE"}
        remaining = _remaining(state, started)
        if remaining <= 0:
            return {"status": "failed", "error": "DEADLINE_EXCEEDED", "remaining_seconds": 0}
        return {"approval_payload": payload, "remaining_seconds": remaining}

    def route_prepared(state: AgentState) -> str:
        return "finalize" if state["status"] == "failed" else "approval"

    async def approval(state: AgentState) -> dict[str, Any]:
        # The caller verifies the decision independently; the resume value is never trusted.
        interrupt(state["approval_payload"])
        started = time.monotonic()
        try:
            budget = min(
                state["remaining_seconds"], max(0.0, state["active_deadline"] - time.monotonic())
            )
            async with asyncio.timeout(budget):
                result = await resolve_approval(state["approval_payload"])
        except TimeoutError:
            return {"status": "failed", "error": "DEADLINE_EXCEEDED", "remaining_seconds": 0}
        except Exception:
            if (
                time.monotonic() >= state["active_deadline"]
                or time.monotonic() - started >= state["remaining_seconds"]
            ):
                return {"status": "failed", "error": "DEADLINE_EXCEEDED", "remaining_seconds": 0}
            logger.exception("agent_approval_resolution_failed")
            return {"status": "failed", "error": "APPROVAL_UNAVAILABLE"}
        remaining = _remaining(state, started)
        call = state["pending_calls"][state["call_index"]]
        return {
            "messages": [
                *state["messages"],
                ToolMessage(content=result.model_dump_json(), tool_call_id=call["id"]),
            ],
            "call_index": state["call_index"] + 1,
            "approval_requested": False,
            "reset_rejected": result.success
            and isinstance(result.data, dict)
            and result.data.get("status") == "rejected",
            "remaining_seconds": remaining,
            "consecutive_failures": 0 if result.success else state["consecutive_failures"] + 1,
            **({"status": "failed", "error": "DEADLINE_EXCEEDED"} if remaining <= 0 else {}),
        }

    def limit(_state: AgentState) -> dict[str, Any]:
        return {"status": "failed", "error": "EXECUTION_LIMIT"}

    def finalize(state: AgentState) -> dict[str, Any]:
        if state["status"] == "failed":
            return {
                "answer": "I could not complete this request. Please try again.",
                "citations": [],
            }
        answer, citations = validate_citations(
            _as_text(state["messages"][-1]),
            [RetrievedChunk.model_validate(item) for item in state["retrieved"]],
        )
        if not answer.strip():
            return {
                "status": "failed",
                "error": "EMPTY_RESPONSE",
                "answer": "I could not complete this request. Please try again.",
                "citations": [],
            }
        return {
            "status": "completed",
            "answer": answer,
            "citations": [item.model_dump(mode="json") for item in citations],
        }

    def count_sync(node: Any) -> Any:
        def run(state: AgentState) -> dict[str, Any]:
            return {**node(state), "steps": 1}

        return run

    def count_async(node: Any) -> Any:
        async def run(state: AgentState) -> dict[str, Any]:
            return {**await node(state), "steps": 1}

        return run

    graph = StateGraph(AgentState)
    for name, node in (("prepare", prepare), ("limit", limit), ("finalize", finalize)):
        graph.add_node(name, count_sync(node))
    for name, node in (
        ("model", call_model),
        ("tools", tools),
        ("prepare_approval", prepare_action),
        ("approval", approval),
    ):
        graph.add_node(name, count_async(node))
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "model")
    graph.add_conditional_edges(
        "model", route_model, {"model": "model", "tools": "tools", "finalize": "finalize"}
    )
    graph.add_conditional_edges(
        "tools",
        route_tools,
        {
            "tools": "tools",
            "model": "model",
            "prepare_approval": "prepare_approval",
            "limit": "limit",
            "finalize": "finalize",
        },
    )
    graph.add_conditional_edges(
        "prepare_approval", route_prepared, {"approval": "approval", "finalize": "finalize"}
    )
    graph.add_conditional_edges(
        "approval",
        route_tools,
        {
            "tools": "tools",
            "model": "model",
            "prepare_approval": "prepare_approval",
            "limit": "limit",
            "finalize": "finalize",
        },
    )
    graph.add_edge("limit", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


def initial_state(
    history: list[MessageData],
    message: str,
    settings: Settings,
    *,
    customer_id: UUID | None = None,
    conversation_id: UUID | None = None,
    run_id: UUID | None = None,
) -> AgentState:
    return {
        "customer_id": str(customer_id) if customer_id else "",
        "conversation_id": str(conversation_id) if conversation_id else "",
        "run_id": str(run_id) if run_id else "",
        "steps": 0,
        "history": [item.model_dump(mode="json") for item in history],
        "current_message": message,
        "messages": [],
        "retrieved": [],
        "pending_calls": [],
        "call_index": 0,
        "llm_calls": 0,
        "tool_calls": 0,
        "retrieval_calls": 0,
        "consecutive_failures": 0,
        "retries": 0,
        "remaining_seconds": settings.active_turn_deadline_seconds,
        "active_deadline": time.monotonic() + settings.active_turn_deadline_seconds,
        "status": "running",
    }
