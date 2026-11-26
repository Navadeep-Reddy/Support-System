"""Coordinate a graph turn with owned runs and product-visible persistence.

Approval decisions are deliberately not accepted here. The future approval endpoint
must validate and record a decision (and execute an approved reset) before resume.
"""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID, uuid4

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from support_agent.agent.context import (
    MODEL_OUTPUT_TOKENS,
    prepare_context,
    validate_context_capacity,
)
from support_agent.agent.graph import build_graph, initial_state
from support_agent.core.config import Settings, get_settings
from support_agent.core.database import get_engine
from support_agent.models import ActionApproval
from support_agent.repositories.conversations import ConversationRepository
from support_agent.schemas.account import ResetResult
from support_agent.schemas.conversation import Citation
from support_agent.services.accounts import AccountService
from support_agent.services.conversations import (
    ConversationError,
    ConversationService,
    approval_card,
)
from support_agent.services.embeddings import EmbeddingService
from support_agent.services.knowledge import KnowledgeService
from support_agent.tools.support import SupportTools, ToolError, ToolResult, tool_definitions

logger = logging.getLogger(__name__)


def make_model(settings: Settings) -> Any:
    return ChatNVIDIA(
        model=settings.llm_model,
        base_url=settings.nvidia_base_url,
        api_key=settings.nvidia_api_key.get_secret_value() or None,
        temperature=0,
        max_completion_tokens=MODEL_OUTPUT_TOKENS,
    ).bind_tools(tool_definitions())


@asynccontextmanager
async def open_agent_turns(engine=None) -> AsyncIterator["AgentTurns"]:
    """Open a PostgreSQL-backed runner; callers retain it across start/resume requests."""
    engine = engine or get_engine()
    settings = get_settings().model_copy(
        update={"database_url": engine.url.render_as_string(hide_password=False)}
    )
    async with AsyncPostgresSaver.from_conn_string(settings.checkpointer_database_uri) as saver:
        await saver.setup()
        yield AgentTurns(sessionmaker(engine, expire_on_commit=False), settings, saver)


class AgentTurns:
    """Own transactions around graph execution; no SQLAlchemy session crosses threads."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        settings: Settings,
        checkpointer: Any,
        model: Any | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.checkpointer = checkpointer
        self.background_tasks: set[asyncio.Task] = set()
        self.model = model if model is not None else make_model(settings)

    def _execute(self, customer_id: UUID, name: str, arguments: dict[str, Any]) -> ToolResult[Any]:
        with self.sessions() as session:
            knowledge = None
            if name == "search_knowledge_base":
                knowledge = KnowledgeService(session, EmbeddingService(self.settings))
            return SupportTools(customer_id, AccountService(session), knowledge).execute(
                name, arguments
            )

    def _prepare(self, customer_id: UUID, run_id: UUID, deadline: float) -> dict[str, Any]:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError("Approval preparation exceeded the active deadline")
        with self.sessions.begin() as session:
            session.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{max(1, int(budget * 1000))}ms"},
            )
            repository = ConversationRepository(session)
            run = repository.owned_run_for_update(customer_id, run_id)
            if run is None or run.status not in ("running", "waiting_for_approval"):
                raise ConversationError("NOT_FOUND", "The active run was not found.")
            action = repository.pending_approval(run_id)
            if action is None:
                action_id = uuid4()
                payload = AccountService(session).prepare_reset(customer_id, action_id)
                action = ActionApproval(
                    id=action_id,
                    run_id=run_id,
                    action_type="request_password_reset",
                    status="pending",
                    validated_payload=payload.model_dump(mode="json"),
                )
                ConversationService(session).add_pending_approval(action)
                ConversationService(session).add_message(
                    customer_id, run_id, "action", None, approval_id=action_id
                )
            run.status = "waiting_for_approval"
            session.flush()
            card = approval_card(action).model_dump(mode="json")
            if time.monotonic() >= deadline:
                raise TimeoutError("Approval preparation exceeded the active deadline")
            return card

    def _resolve(self, customer_id: UUID, run_id: UUID, payload: dict[str, Any]) -> ToolResult[Any]:
        with self.sessions() as session:
            run = ConversationRepository(session).owned_run_for_update(customer_id, run_id)
            action = session.get(ActionApproval, UUID(payload["action_id"]))
            if run is None or action is None or action.run_id != run_id:
                raise ConversationError("NOT_FOUND", "The action was not found.")
            if action.status == "rejected":
                return ToolResult(
                    success=True,
                    data={
                        "status": "rejected",
                        "reason": "customer_cancelled",
                        "message": "The customer cancelled the confirmation. "
                        "No reset request was created.",
                    },
                )
            if action.status == "executed":
                return ToolResult(
                    success=True, data=ResetResult.model_validate(action.execution_result)
                )
            return ToolResult(
                success=False,
                error=ToolError(
                    code="APPROVAL_UNRESOLVED", message="The action was not completed."
                ),
            )

    def _graph(self, customer_id: UUID, run_id: UUID):
        async def execute(name: str, arguments: dict[str, Any]) -> ToolResult[Any]:
            return await asyncio.to_thread(self._execute, customer_id, name, arguments)

        async def prepare(budget: float) -> dict[str, Any]:
            # Drain the bounded transaction on cancellation before failing the run;
            # otherwise a worker could commit a pending card after cleanup.
            deadline = time.monotonic() + budget
            task = asyncio.create_task(
                asyncio.to_thread(self._prepare, customer_id, run_id, deadline)
            )
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:
                    await task
                except Exception:
                    logger.warning("cancelled_approval_prepare_failed")
                raise

        async def resolve(payload: dict[str, Any]) -> ToolResult[Any]:
            return await asyncio.to_thread(self._resolve, customer_id, run_id, payload)

        return build_graph(self.model, execute, prepare, resolve, self.settings, self.checkpointer)

    def _finish(
        self,
        customer_id: UUID,
        run_id: UUID,
        state: dict[str, Any],
        deadline: float | None = None,
    ) -> None:
        with self.sessions.begin() as session:
            if deadline is not None:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise TimeoutError("Finalization exceeded the active deadline")
                session.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{max(1, int(budget * 1000))}ms"},
                )
            repository = ConversationRepository(session)
            run = repository.owned_run_for_update(customer_id, run_id)
            if run is None:
                raise ConversationError("NOT_FOUND", "The run was not found.")
            if run.status not in ("running", "waiting_for_approval"):
                return
            service = ConversationService(session)
            if state.get("status") == "completed":
                citations = [Citation.model_validate(item) for item in state.get("citations", [])]
                sources = [Citation.model_validate(item) for item in state.get("retrieved", [])]
                service.add_message(
                    customer_id,
                    run_id,
                    "assistant",
                    state["answer"],
                    citations=citations,
                    retrieved=sources,
                )
                service.set_run_status(customer_id, run_id, "completed")
            else:
                pending = repository.pending_approval(run_id)
                if pending:
                    pending.status = "failed"
                service.add_message(
                    customer_id,
                    run_id,
                    "assistant",
                    "I couldn't finish responding. Check any action card for its recorded "
                    "outcome before trying again.",
                )
                service.set_run_status(customer_id, run_id, "failed")
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError("Finalization exceeded the active deadline")

    async def start(self, customer_id: UUID, conversation_id: UUID, message: str) -> dict[str, Any]:
        started = time.monotonic()
        with self.sessions.begin() as session:
            service = ConversationService(session)
            history = service.history(customer_id, conversation_id).messages
            context = prepare_context(history, message, self.settings.history_token_budget)
            validate_context_capacity(context, self.settings.model_context_token_budget)
            run = service.reserve_run(customer_id, conversation_id)
            service.add_message(customer_id, run.id, "user", message)
        state = initial_state(
            history,
            message,
            self.settings,
            customer_id=customer_id,
            conversation_id=conversation_id,
            run_id=run.id,
        )
        state["remaining_seconds"] = max(
            0, state["remaining_seconds"] - (time.monotonic() - started)
        )
        state["active_deadline"] = started + self.settings.active_turn_deadline_seconds
        return await self._invoke(
            customer_id, run.id, state, state["remaining_seconds"], conversation_id=conversation_id
        )

    async def decision_deadline(
        self, customer_id: UUID, run_id: UUID, action_id: UUID, started: float
    ) -> float:
        """Read the saved active budget and ensure this is the interrupted action."""
        budget = self.settings.active_turn_deadline_seconds - (time.monotonic() - started)
        async with asyncio.timeout(max(0.0, budget)):
            snapshot = await self._graph(customer_id, run_id).aget_state(
                {"configurable": {"thread_id": str(run_id)}}
            )
        payload = snapshot.values.get("approval_payload", {})
        if str(payload.get("action_id")) != str(action_id):
            raise ConversationError("APPROVAL_RESOLVED", "The action is no longer pending.")
        return started + snapshot.values["remaining_seconds"]

    def fail_pending_decision(self, customer_id: UUID, run_id: UUID, action_id: UUID) -> bool:
        with self.sessions.begin() as session:
            repository = ConversationRepository(session)
            run = repository.owned_run_for_update(customer_id, run_id)
            pending = repository.pending_approval(run_id) if run else None
            if (
                run is None
                or run.status != "waiting_for_approval"
                or not pending
                or pending.id != action_id
            ):
                return False
            pending.status = "failed"
            service = ConversationService(session)
            service.add_message(
                customer_id,
                run_id,
                "assistant",
                "I couldn't finish the request before the deadline. No reset was made.",
            )
            service.set_run_status(customer_id, run_id, "failed")
            return True

    def _activate_resume(
        self, customer_id: UUID, run_id: UUID, payload: dict[str, Any], deadline: float
    ) -> None:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError("Decision processing exceeded the active deadline")
        try:
            with self.sessions.begin() as session:
                session.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": f"{max(1, int(budget * 1000))}ms"},
                )
                repository = ConversationRepository(session)
                run = repository.owned_run_for_update(customer_id, run_id)
                if run is None:
                    raise ConversationError("NOT_FOUND", "The run was not found.")
                if run.status not in ("waiting_for_approval", "running"):
                    raise ConversationError("RUN_RESOLVED", "The run cannot be resumed.")
                action = session.get(ActionApproval, UUID(payload["action_id"]))
                if (
                    action is None
                    or action.run_id != run_id
                    or action.status not in ("rejected", "executed", "failed")
                ):
                    raise ConversationError("APPROVAL_REQUIRED", "The action has not been decided.")
                run.status = "running"
                session.flush()
                if time.monotonic() >= deadline:
                    raise TimeoutError("Decision processing exceeded the active deadline")
        except Exception as exc:
            if getattr(getattr(exc, "orig", None), "sqlstate", None) == "57014":
                raise TimeoutError("Decision processing exceeded the active deadline") from exc
            raise

    async def _settle_abandoned_activation(
        self, task: asyncio.Task, customer_id: UUID, run_id: UUID
    ) -> None:
        try:
            await task
        except Exception:
            logger.warning("abandoned_resume_activation_failed run_id=%s", run_id, exc_info=True)
        await asyncio.to_thread(self._finish, customer_id, run_id, {"status": "failed"})

    async def resume(
        self, customer_id: UUID, run_id: UUID, *, active_started_at: float
    ) -> dict[str, Any]:
        """Resume after a verified decision; include decision processing in the budget.

        Callers that process a decision first must pass their monotonic start time.
        """
        started = active_started_at
        graph = self._graph(customer_id, run_id)
        config = {"configurable": {"thread_id": str(run_id)}}
        abandoned = False
        try:
            initial_budget = max(
                0.0, self.settings.active_turn_deadline_seconds - (time.monotonic() - started)
            )
            async with asyncio.timeout(initial_budget):
                snapshot = await graph.aget_state(config)
            if not snapshot.values:
                raise ConversationError("RUN_RESOLVED", "The run is not waiting for approval.")
            deadline = started + snapshot.values["remaining_seconds"]
            remaining = max(0.0, deadline - time.monotonic())
            payload = snapshot.values.get("approval_payload", {})
            task = asyncio.create_task(
                asyncio.to_thread(self._activate_resume, customer_id, run_id, payload, deadline)
            )
            try:
                async with asyncio.timeout(remaining):
                    await asyncio.shield(task)
            except (TimeoutError, asyncio.CancelledError) as exc:
                abandoned = True
                cleanup = asyncio.create_task(
                    self._settle_abandoned_activation(task, customer_id, run_id)
                )
                self.background_tasks.add(cleanup)
                cleanup.add_done_callback(self.background_tasks.discard)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise ConversationError(
                    "DECISION_PENDING", "The decision outcome is being resolved. Refresh history."
                ) from exc
        except asyncio.CancelledError:
            if not abandoned:
                self._finish(customer_id, run_id, {"status": "failed"})
            raise
        except TimeoutError:
            self._finish(customer_id, run_id, {"status": "failed"})
            return {"run_id": run_id, "status": "failed", "error": "DEADLINE_EXCEEDED"}
        return await self._invoke(
            customer_id,
            run_id,
            Command(resume=True),
            max(0.0, deadline - time.monotonic()),
            graph=graph,
            conversation_id=UUID(snapshot.values["conversation_id"]),
        )

    async def _invoke(
        self,
        customer_id: UUID,
        run_id: UUID,
        graph_input: Any,
        budget: float,
        graph: Any | None = None,
        conversation_id: UUID | None = None,
    ) -> dict[str, Any]:
        graph = graph or self._graph(customer_id, run_id)
        config = {
            "configurable": {"thread_id": str(run_id)},
            "metadata": {"run_id": str(run_id), "conversation_id": str(conversation_id or "")},
            "recursion_limit": 2 * (self.settings.max_llm_calls + self.settings.max_tool_calls)
            + 20,
        }
        started = time.monotonic()
        try:
            async with asyncio.timeout(budget):
                if isinstance(graph_input, Command):
                    await graph.aupdate_state(config, {"active_deadline": started + budget})
                result = await graph.ainvoke(graph_input, config)
                if result.get("__interrupt__"):
                    remaining = max(0.0, budget - (time.monotonic() - started))
                    if remaining <= 0:
                        raise TimeoutError
                    await graph.aupdate_state(config, {"remaining_seconds": remaining})
                    return {"run_id": run_id, "status": "waiting_for_approval", "error": None}
            try:
                self._finish(customer_id, run_id, result, started + budget)
            except Exception as exc:
                if getattr(getattr(exc, "orig", None), "sqlstate", None) == "57014":
                    raise TimeoutError("Finalization exceeded the active deadline") from exc
                raise
            return {"run_id": run_id, "status": result["status"], "error": result.get("error")}
        except asyncio.CancelledError:
            self._finish(customer_id, run_id, {"status": "failed"})
            raise
        except Exception as exc:
            logger.exception("agent_turn_failed", extra={"run_id": str(run_id)})
            self._finish(customer_id, run_id, {"status": "failed"})
            return {
                "run_id": run_id,
                "status": "failed",
                "error": "DEADLINE_EXCEEDED" if isinstance(exc, TimeoutError) else "INTERNAL_ERROR",
            }
