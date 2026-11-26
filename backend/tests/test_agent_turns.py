import asyncio
import time
from collections import deque
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import create_engine, delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from support_agent.agent.context import ContextError
from support_agent.core.config import get_settings
from support_agent.core.schema import initialize_schema
from support_agent.models import ActionApproval, Conversation, Customer, PasswordResetRequest
from support_agent.schemas.knowledge import RetrievedChunk
from support_agent.services.accounts import AccountService
from support_agent.services.agent_turns import AgentTurns
from support_agent.services.conversations import ConversationError, ConversationService
from support_agent.tools.support import SearchResults, ToolResult


class Model:
    def __init__(self, replies):
        self.replies = deque(replies)
        self.inputs = []

    async def ainvoke(self, messages):
        self.inputs.append(messages)
        return self.replies.popleft()


@pytest.fixture
def customer_db():
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    customer_id, conversation_id = uuid4(), uuid4()
    with sessions.begin() as session:
        session.add(Customer(id=customer_id, handle=f"test-{uuid4()}", display_name="Test"))
        session.flush()
        session.add(Conversation(id=conversation_id, customer_id=customer_id, title="Test"))
    yield sessions, customer_id, conversation_id
    with sessions.begin() as session:
        session.execute(
            delete(PasswordResetRequest).where(PasswordResetRequest.customer_id == customer_id)
        )
        session.execute(delete(Customer).where(Customer.id == customer_id))
    engine.dispose()


def test_pending_approval_survives_wait_and_resume_rejection(customer_db):
    sessions, customer_id, conversation_id = customer_db

    async def run():
        model = Model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "request_password_reset",
                            "args": {},
                            "id": "reset",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Cancelled."),
            ]
        )
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
        paused = await runner.start(customer_id, conversation_id, "Reset my password")
        assert paused["status"] == "waiting_for_approval"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.pending_approval.status == "pending"
            action_id = history.pending_approval.action_id
            assert session.scalar(select(PasswordResetRequest)) is None
        with pytest.raises(ConversationError):
            await runner.resume(customer_id, paused["run_id"], active_started_at=time.monotonic())
        with sessions.begin() as session:
            action = session.get(ActionApproval, action_id)
            action.status = "rejected"
            action.decided_at = datetime.now(UTC)
        result = await runner.resume(
            customer_id, paused["run_id"], active_started_at=time.monotonic()
        )
        assert result["status"] == "completed"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert [m.role for m in history.messages] == ["user", "action", "assistant"]
            assert history.messages[1].approval.status == "rejected"
            assert session.scalar(select(PasswordResetRequest)) is None

    asyncio.run(run())


def test_failed_final_generation_preserves_committed_reset(customer_db):
    sessions, customer_id, conversation_id = customer_db

    class FailingModel:
        def __init__(self):
            self.count = 0

        async def ainvoke(self, messages):
            self.count += 1
            if self.count == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "request_password_reset",
                            "args": {},
                            "id": "reset",
                            "type": "tool_call",
                        }
                    ],
                )
            raise ValueError("invalid provider response")

    async def run():
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), FailingModel())
        paused = await runner.start(customer_id, conversation_id, "Reset my password")
        with sessions.begin() as session:
            action = session.scalar(
                select(ActionApproval).where(ActionApproval.run_id == paused["run_id"])
            )
            action.status = "approved"
            action.decided_at = datetime.now(UTC)
            action_id = action.id
            reset = AccountService(session).execute_reset(customer_id, action_id)
        result = await runner.resume(
            customer_id, paused["run_id"], active_started_at=time.monotonic()
        )
        assert result["status"] == "failed"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert history.messages[1].approval.status == "executed"
            assert history.messages[1].approval.result.request_id == reset.request_id
            assert (
                session.scalar(
                    select(PasswordResetRequest).where(PasswordResetRequest.action_id == action_id)
                )
                is not None
            )

    asyncio.run(run())


def test_citations_persist_only_actual_current_run_sources(customer_db):
    sessions, customer_id, conversation_id = customer_db

    async def run():
        source = RetrievedChunk(
            article_id=uuid4(),
            chunk_id=uuid4(),
            article_title="Refund",
            section="Terms",
            category="billing",
            text="Fourteen days",
            score=0.9,
        )
        fabricated = uuid4()
        model = Model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "search_knowledge_base",
                            "id": "search",
                            "args": {"query": "refund"},
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content=f"Policy [source:{source.chunk_id}] fake [source:{fabricated}]"),
            ]
        )
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
        runner._execute = lambda *args: ToolResult(
            success=True, data=SearchResults(chunks=[source])
        )
        result = await runner.start(customer_id, conversation_id, "refund?")
        assert result["status"] == "completed"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert len(history.messages[-1].citations) == 1
            assert history.messages[-1].citations[0].chunk_id == source.chunk_id
            assert str(fabricated) not in history.messages[-1].content

    asyncio.run(run())


def test_postgres_checkpoint_survives_reconnection(customer_db):
    sessions, customer_id, conversation_id = customer_db
    uri = (
        make_url(get_settings().test_database_url)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )

    async def run():
        model = Model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "request_password_reset",
                            "args": {},
                            "id": "reset",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Cancelled."),
            ]
        )
        async with AsyncPostgresSaver.from_conn_string(uri) as saver:
            await saver.setup()
            runner = AgentTurns(sessions, get_settings(), saver, model)
            paused = await runner.start(customer_id, conversation_id, "Reset my password")
            assert paused["status"] == "waiting_for_approval"
            run_id = paused["run_id"]
            config = {"configurable": {"thread_id": str(run_id)}}
            snapshot = await runner._graph(customer_id, run_id).aget_state(config)
            remaining = snapshot.values["remaining_seconds"]
        try:
            await asyncio.sleep(0.05)
            with sessions.begin() as session:
                action = session.scalar(
                    select(ActionApproval).where(ActionApproval.run_id == run_id)
                )
                action.status = "rejected"
                action.decided_at = datetime.now(UTC)
            async with AsyncPostgresSaver.from_conn_string(uri) as saver:
                runner = AgentTurns(sessions, get_settings(), saver, model)
                snapshot = await runner._graph(customer_id, run_id).aget_state(config)
                assert snapshot.values["remaining_seconds"] == remaining
                result = await runner.resume(
                    customer_id, run_id, active_started_at=time.monotonic()
                )
                assert result["status"] == "completed"
        finally:
            async with AsyncPostgresSaver.from_conn_string(uri) as saver:
                await saver.adelete_thread(str(run_id))

    asyncio.run(run())


def test_resume_uses_remaining_budget_and_preserves_outcome(customer_db):
    sessions, customer_id, conversation_id = customer_db

    class SlowAfterPause:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, messages):
            self.calls += 1
            if self.calls == 1:
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "request_password_reset",
                            "args": {},
                            "id": "reset",
                            "type": "tool_call",
                        }
                    ],
                )
            await asyncio.sleep(1)
            return AIMessage(content="late")

    async def run():
        saver = InMemorySaver()
        runner = AgentTurns(sessions, get_settings(), saver, SlowAfterPause())
        paused = await runner.start(customer_id, conversation_id, "Reset my password")
        run_id = paused["run_id"]
        cfg = {"configurable": {"thread_id": str(run_id)}}
        await runner._graph(customer_id, run_id).aupdate_state(cfg, {"remaining_seconds": 0.05})
        with sessions.begin() as session:
            action = session.scalar(select(ActionApproval).where(ActionApproval.run_id == run_id))
            action.status = "approved"
            action.decided_at = datetime.now(UTC)
            action_id = action.id
            reset = AccountService(session).execute_reset(customer_id, action_id)
        await asyncio.sleep(0.1)  # Approval waiting time is not active execution.
        result = await runner.resume(customer_id, run_id, active_started_at=time.monotonic())
        assert result["status"] == "failed"
        assert result["error"] == "DEADLINE_EXCEEDED"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert history.messages[1].approval.result.request_id == reset.request_id
            assert "recorded outcome" in history.messages[-1].content

    asyncio.run(run())


def test_timeout_during_resume_verification_fails_run_and_keeps_result(customer_db):
    sessions, customer_id, conversation_id = customer_db

    async def run():
        runner = AgentTurns(
            sessions,
            get_settings(),
            InMemorySaver(),
            Model(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "request_password_reset",
                                "args": {},
                                "id": "reset",
                                "type": "tool_call",
                            }
                        ],
                    )
                ]
            ),
        )
        paused = await runner.start(customer_id, conversation_id, "Reset my password")
        run_id = paused["run_id"]
        graph = runner._graph(customer_id, run_id)
        await graph.aupdate_state(
            {"configurable": {"thread_id": str(run_id)}}, {"remaining_seconds": 0.05}
        )
        with sessions.begin() as session:
            action = session.scalar(select(ActionApproval).where(ActionApproval.run_id == run_id))
            action.status = "approved"
            action.decided_at = datetime.now(UTC)
            result = AccountService(session).execute_reset(customer_id, action.id)
        original = runner._activate_resume

        def slow_activation(*args):
            time.sleep(0.1)
            return original(*args)

        runner._activate_resume = slow_activation
        failed = await runner.resume(customer_id, run_id, active_started_at=time.monotonic())
        assert failed["status"] == "failed"
        assert failed["error"] == "DEADLINE_EXCEEDED"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert history.messages[1].approval.result.request_id == result.request_id
        # An old checkpoint cannot reactivate a failed run.
        runner._activate_resume = original
        with pytest.raises(ConversationError):
            await runner.resume(customer_id, run_id, active_started_at=time.monotonic())

    asyncio.run(run())


def test_timeout_during_approval_does_not_commit_late_card(customer_db):
    sessions, customer_id, conversation_id = customer_db

    async def run():
        settings = get_settings().model_copy(update={"active_turn_deadline_seconds": 0.05})
        model = Model(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "request_password_reset",
                            "args": {},
                            "id": "reset",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        )
        runner = AgentTurns(sessions, settings, InMemorySaver(), model)
        original_prepare = runner._prepare

        def slow_prepare(*args):
            time.sleep(0.1)
            return original_prepare(*args)

        runner._prepare = slow_prepare
        result = await runner.start(customer_id, conversation_id, "Reset my password")
        assert result["status"] == "failed"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert history.pending_approval is None
            assert (
                session.scalar(
                    select(ActionApproval).where(ActionApproval.run_id == result["run_id"])
                )
                is None
            )

    asyncio.run(run())


def test_foreign_conversation_never_reaches_model(customer_db):
    sessions, _, conversation_id = customer_db

    async def run():
        model = Model([])
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
        with pytest.raises(ConversationError):
            await runner.start(uuid4(), conversation_id, "What is my payment?")
        assert model.inputs == []

    asyncio.run(run())


def test_context_capacity_rejected_before_reserving_run(customer_db):
    sessions, customer_id, conversation_id = customer_db

    async def run():
        settings = get_settings().model_copy(update={"model_context_token_budget": 100})
        runner = AgentTurns(sessions, settings, InMemorySaver(), Model([]))
        with pytest.raises(ContextError):
            await runner.start(customer_id, conversation_id, "Hello")
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert history.messages == []

    asyncio.run(run())


def test_deadline_includes_persisting_final_response(customer_db):
    sessions, customer_id, conversation_id = customer_db

    async def run():
        settings = get_settings().model_copy(update={"active_turn_deadline_seconds": 0.05})
        runner = AgentTurns(sessions, settings, InMemorySaver(), Model([AIMessage(content="Done")]))
        original = runner._finish

        def slow_finish(customer, run_id, state, deadline=None):
            if deadline is not None:
                time.sleep(0.1)
            return original(customer, run_id, state, deadline)

        runner._finish = slow_finish
        result = await runner.start(customer_id, conversation_id, "Hello")
        assert result["status"] == "failed"
        assert result["error"] == "DEADLINE_EXCEEDED"
        with sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
            assert history.active_run is None
            assert history.messages[-1].content != "Done"

    asyncio.run(run())


def test_deadline_fails_run_and_releases_lock(customer_db):
    sessions, customer_id, conversation_id = customer_db

    class SlowModel:
        async def ainvoke(self, messages):
            await asyncio.sleep(1)
            return AIMessage(content="late")

    async def run():
        settings = get_settings().model_copy(update={"active_turn_deadline_seconds": 0.05})
        runner = AgentTurns(sessions, settings, InMemorySaver(), SlowModel())
        result = await runner.start(customer_id, conversation_id, "Help")
        assert result["status"] == "failed"
        assert result["error"] == "DEADLINE_EXCEEDED"
        with sessions() as session:
            assert (
                ConversationService(session).history(customer_id, conversation_id).active_run
                is None
            )

    asyncio.run(run())
