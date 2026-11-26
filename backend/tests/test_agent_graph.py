import asyncio
from collections import deque
from uuid import uuid4

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from support_agent.agent.graph import build_graph, initial_state
from support_agent.core.config import Settings
from support_agent.tools.support import ApprovalRequired, ToolError, ToolResult


class Model:
    def __init__(self, responses):
        self.responses = deque(responses)
        self.inputs = []

    async def ainvoke(self, messages):
        self.inputs.append(messages)
        response = self.responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response


def call(name, identifier, args=None):
    return {"name": name, "id": identifier, "args": args or {}, "type": "tool_call"}


def test_tool_calls_are_sequential_and_paired_across_approval():
    async def run():
        model = Model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        call("get_payment_status", "one"),
                        call("request_password_reset", "two"),
                        call("get_current_subscription", "three"),
                    ],
                ),
                AIMessage(content="Done"),
            ]
        )
        calls = []

        async def execute(name, args):
            calls.append(name)
            data = ApprovalRequired() if name == "request_password_reset" else {"status": "ok"}
            return ToolResult(success=True, data=data)

        async def prepare(budget):
            return {"action_id": "backend-generated"}

        async def resolve(payload):
            return ToolResult(success=True, data={"status": "rejected"})

        graph = build_graph(model, execute, prepare, resolve, Settings(), InMemorySaver())
        config = {"configurable": {"thread_id": str(uuid4())}}
        paused = await graph.ainvoke(initial_state([], "help", Settings()), config)
        assert paused["__interrupt__"][0].value == {"action_id": "backend-generated"}
        assert calls == ["get_payment_status", "request_password_reset"]
        done = await graph.ainvoke(Command(resume={"approved": True}), config)
        assert done["status"] == "completed"
        assert calls == ["get_payment_status", "request_password_reset", "get_current_subscription"]
        assert [m.tool_call_id for m in model.inputs[-1] if isinstance(m, ToolMessage)] == [
            "one",
            "two",
            "three",
        ]
        assert "rejected" in model.inputs[-1][-2].content

    asyncio.run(run())


def test_limits_and_retries():
    async def run():
        settings = Settings(
            max_llm_calls=3, max_provider_retries=2, max_consecutive_tool_failures=2
        )
        model = Model(
            [TimeoutError(), AIMessage(content="", tool_calls=[call("bad", "1"), call("bad", "2")])]
        )

        async def execute(name, args):
            return ToolResult(success=False, error=ToolError(code="UNKNOWN_TOOL", message="No"))

        async def unused(*args):
            raise AssertionError("unexpected approval")

        graph = build_graph(model, execute, unused, unused, settings, InMemorySaver())
        result = await graph.ainvoke(
            initial_state([], "help", settings), {"configurable": {"thread_id": str(uuid4())}}
        )
        assert result["status"] == "failed"
        assert result["error"] == "TOOL_FAILURE_LIMIT"
        assert result["llm_calls"] == 2
        assert result["tool_calls"] == 2

    asyncio.run(run())
