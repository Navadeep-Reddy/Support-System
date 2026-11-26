import asyncio
import time
from collections import deque
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from support_agent.agent.graph import build_graph, initial_state
from support_agent.core.config import Settings
from support_agent.tools.support import ApprovalRequired, SearchResults, ToolError, ToolResult


class Model:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        reply = self.replies.popleft()
        if isinstance(reply, Exception):
            raise reply
        return reply


def ai_call(name, count=1):
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": {}, "id": str(i), "type": "tool_call"} for i in range(count)
        ],
    )


async def unused(*args):
    raise AssertionError("Unexpected approval")


def config():
    return {"configurable": {"thread_id": str(uuid4())}}


@pytest.mark.parametrize(
    "error,expected", [(Exception("[503] busy"), 3), (Exception("[400] invalid"), 1)]
)
def test_transient_only_retries(error, expected):
    async def run():
        model = Model([error] * 3)
        settings = Settings(max_provider_retries=2)

        async def execute(*args):
            raise AssertionError

        graph = build_graph(model, execute, unused, unused, settings, InMemorySaver())
        result = await graph.ainvoke(initial_state([], "hello", settings), config())
        assert result["status"] == "failed"
        assert result["llm_calls"] == expected == model.calls

    asyncio.run(run())


def test_llm_tool_and_retrieval_limits():
    async def run():
        async def execute(name, args):
            return ToolResult(success=True, data=SearchResults(chunks=[]))

        for settings, reply, expected_calls in [
            (Settings(max_tool_calls=2), ai_call("search_knowledge_base", 3), 3),
            (Settings(max_retrieval_calls=1), ai_call("search_knowledge_base", 2), 2),
            (Settings(max_llm_calls=1), ai_call("search_knowledge_base"), 1),
        ]:
            graph = build_graph(Model([reply]), execute, unused, unused, settings, InMemorySaver())
            result = await graph.ainvoke(initial_state([], "hello", settings), config())
            assert result["status"] == "failed"
            assert result["error"] == "EXECUTION_LIMIT"
            assert result["tool_calls"] == expected_calls

    asyncio.run(run())


def test_rejected_reset_cannot_trigger_another_card_in_same_turn():
    async def run():
        model = Model(
            [
                ai_call("request_password_reset"),
                ai_call("request_password_reset"),
                AIMessage(content="Reset cancelled."),
            ]
        )
        prepared = []

        async def execute(name, args):
            return ToolResult(success=True, data=ApprovalRequired())

        async def prepare(budget):
            prepared.append(1)
            return {"id": "safe"}

        async def resolve(payload):
            return ToolResult(success=True, data={"status": "rejected"})

        settings = Settings()
        graph = build_graph(model, execute, prepare, resolve, settings, InMemorySaver())
        cfg = config()
        paused = await graph.ainvoke(initial_state([], "reset", settings), cfg)
        assert paused.get("__interrupt__")
        result = await graph.ainvoke(Command(resume=True), cfg)
        assert result["status"] == "completed"
        assert prepared == [1]
        assert any("ACTION_REJECTED" in str(message.content) for message in result["messages"])

    asyncio.run(run())


def test_failed_approval_resolution_obeys_failure_limit():
    async def run():
        model = Model([ai_call("request_password_reset"), AIMessage(content="should not run")])

        async def execute(name, args):
            return ToolResult(success=True, data=ApprovalRequired())

        async def prepare(budget):
            return {"action_id": "safe"}

        async def resolve(payload):
            return ToolResult(success=False, error=ToolError(code="FAILED", message="Failed"))

        settings = Settings(max_consecutive_tool_failures=1)
        graph = build_graph(model, execute, prepare, resolve, settings, InMemorySaver())
        cfg = config()
        await graph.ainvoke(initial_state([], "reset", settings), cfg)
        result = await graph.ainvoke(Command(resume=True), cfg)
        assert result["status"] == "failed"
        assert model.calls == 1

    asyncio.run(run())


def test_invalid_tool_calls_count_as_failures_without_execution():
    async def run():
        model = Model(
            [
                AIMessage(
                    content="",
                    invalid_tool_calls=[
                        {
                            "name": "request_password_reset",
                            "args": "{bad",
                            "id": "broken",
                            "error": "json",
                        },
                        {
                            "name": "search_knowledge_base",
                            "args": "{bad",
                            "id": "broken2",
                            "error": "json",
                        },
                    ],
                )
            ]
        )

        async def execute(*args):
            raise AssertionError("invalid tool calls must not execute")

        settings = Settings()
        graph = build_graph(model, execute, unused, unused, settings, InMemorySaver())
        result = await graph.ainvoke(initial_state([], "hello", settings), config())
        assert result["status"] == "failed"
        assert result["error"] == "TOOL_FAILURE_LIMIT"
        assert result["tool_calls"] == 2
        assert result["retrieval_calls"] == 1

    asyncio.run(run())


def test_tool_exception_after_deadline_is_reported_as_deadline():
    async def run():
        async def late_failure(name, args):
            time.sleep(0.03)
            raise RuntimeError("late")

        settings = Settings(active_turn_deadline_seconds=0.01)
        graph = build_graph(
            Model([ai_call("get_payment_status")]),
            late_failure,
            unused,
            unused,
            settings,
            InMemorySaver(),
        )
        result = await graph.ainvoke(initial_state([], "hello", settings), config())
        assert result["status"] == "failed"
        assert result["error"] == "DEADLINE_EXCEEDED"

    asyncio.run(run())


def test_model_timeout_stops_safely():
    async def run():
        class Slow:
            async def ainvoke(self, messages):
                await asyncio.sleep(1)

        settings = Settings(llm_timeout_seconds=0.01, max_provider_retries=0)
        graph = build_graph(Slow(), unused, unused, unused, settings, InMemorySaver())
        result = await graph.ainvoke(initial_state([], "hello", settings), config())
        assert result["status"] == "failed"
        assert result["error"] == "PROVIDER_UNAVAILABLE"
        assert result["llm_calls"] == 1

    asyncio.run(run())
