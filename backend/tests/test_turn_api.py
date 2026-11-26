import asyncio
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

from support_agent.api.conversations import get_turn_service
from support_agent.core.config import get_settings
from support_agent.core.database import get_db_session
from support_agent.core.schema import initialize_schema
from support_agent.main import app
from support_agent.models import ActionApproval, Customer, PasswordResetRequest
from support_agent.services.agent_turns import AgentTurns
from support_agent.services.turns import TurnService


class Model:
    def __init__(self):
        self.replies = deque()

    async def ainvoke(self, messages):
        result = self.replies.popleft()
        if isinstance(result, Exception):
            raise result
        return result


def reset_call():
    return AIMessage(
        content="",
        tool_calls=[
            {"name": "request_password_reset", "args": {}, "id": "reset", "type": "tool_call"}
        ],
    )


@pytest.fixture
def api():
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    ids = [uuid4(), uuid4()]
    with sessions.begin() as session:
        for id in ids:
            session.add(Customer(id=id, handle=f"test-{id}", display_name="Test"))

    def database():
        with sessions() as session:
            yield session

    model = Model()
    runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_turn_service] = lambda: TurnService(runner)
    client = TestClient(app)
    yield client, model, sessions, ids
    app.dependency_overrides.clear()
    client.close()
    with sessions.begin() as session:
        session.execute(
            delete(PasswordResetRequest).where(PasswordResetRequest.customer_id.in_(ids))
        )
        session.execute(delete(Customer).where(Customer.id.in_(ids)))
    engine.dispose()


def login(client, id):
    assert client.post("/sessions", json={"customer_id": str(id)}).status_code == 200


def create(client):
    response = client.post("/conversations", json={})
    assert response.status_code == 201
    return response.json()["id"]


def test_contract_endpoints_are_in_openapi(api):
    client, _, _, _ = api
    paths = client.get("/openapi.json").json()["paths"]
    endpoints = {
        "/customers": {"get"},
        "/sessions": {"post"},
        "/sessions/current": {"delete"},
        "/knowledge/session": {"get", "post"},
        "/me": {"get"},
        "/conversations": {"get", "post"},
        "/conversations/{conversation_id}/messages": {"get"},
        "/conversations/{conversation_id}/chat": {"post"},
        "/approvals/{action_id}": {"post"},
        "/messages/{message_id}/feedback": {"put"},
        "/knowledge/articles": {"get", "post"},
        "/knowledge/articles/{article_id}": {"get", "put", "delete"},
    }
    assert sum(map(len, endpoints.values())) == 17
    for path, methods in endpoints.items():
        assert methods <= paths[path].keys()
    responses = paths["/approvals/{action_id}"]["post"]["responses"]
    assert responses["409"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorEnvelope"
    )
    assert responses["422"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/ErrorEnvelope"
    )
    assert client.get("/docs").status_code == 200


def test_http_approve_refresh_ownership_and_duplicate(api):
    client, model, sessions, ids = api
    login(client, ids[0])
    conversation = create(client)
    model.replies.extend([reset_call(), AIMessage(content="Reset requested.")])
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    assert pending["status"] == "waiting_for_approval"
    action = pending["pending_approval"]["action_id"]
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.customer_id == ids[0])
            )
            == 0
        )
    history = client.get(f"/conversations/{conversation}/messages").json()
    assert history["pending_approval"]["action_id"] == action
    assert (
        client.post(f"/conversations/{conversation}/chat", json={"message": "Again"}).status_code
        == 409
    )
    other = create(client)
    model.replies.appendleft(AIMessage(content="Hello."))
    assert (
        client.post(f"/conversations/{other}/chat", json={"message": "Hello"}).json()["status"]
        == "completed"
    )
    assert (
        client.post(
            f"/approvals/{action}", json={"approved": True, "customer_id": str(ids[0])}
        ).status_code
        == 422
    )
    login(client, ids[1])
    assert client.post(f"/approvals/{action}", json={"approved": True}).status_code == 404
    assert client.get(f"/conversations/{conversation}/messages").status_code == 404
    login(client, ids[0])
    response = client.post(f"/approvals/{action}", json={"approved": True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed"
    assert result["run_id"] == pending["run_id"]
    card = next(m["approval"] for m in result["messages"] if m["role"] == "action")
    assert card["status"] == "executed" and card["result"]["simulated"] is True
    assert client.post(f"/approvals/{action}", json={"approved": True}).status_code == 409
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.action_id == action)
            )
            == 1
        )
    assert client.get(f"/conversations/{conversation}/messages").json()["active_run"] is None


def test_decision_deadline_expires_without_reset(api):
    client, model, sessions, ids = api
    login(client, ids[0])
    conversation = create(client)
    model.replies.append(reset_call())
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    action = pending["pending_approval"]["action_id"]
    runner = app.dependency_overrides[get_turn_service]().runner
    graph = runner._graph(ids[0], pending["run_id"])
    asyncio.run(
        graph.aupdate_state(
            {"configurable": {"thread_id": pending["run_id"]}}, {"remaining_seconds": 0.000001}
        )
    )
    response = client.post(f"/approvals/{action}", json={"approved": True})
    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["error"]["code"] == "DEADLINE_EXCEEDED"
    assert response.json()["messages"][1]["approval"]["status"] == "failed"
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.action_id == action)
            )
            == 0
        )


@pytest.mark.parametrize("commit_first", [False, True])
def test_stalled_decision_returns_promptly_and_reconciles(api, commit_first):
    _, model, sessions, ids = api

    async def run():
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
        turns = TurnService(runner)
        app.dependency_overrides[get_turn_service] = lambda: turns
        release = Event()
        original = turns._decide

        def stalled(*args):
            if commit_first:
                original(*args)
            assert release.wait(timeout=5)
            if not commit_first:
                original(*args)

        turns._decide = stalled
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/sessions", json={"customer_id": str(ids[0])})
            conversation = (await client.post("/conversations", json={})).json()["id"]
            model.replies.append(reset_call())
            pending = (
                await client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"})
            ).json()
            action = pending["pending_approval"]["action_id"]
            await runner._graph(ids[0], pending["run_id"]).aupdate_state(
                {"configurable": {"thread_id": pending["run_id"]}},
                {"remaining_seconds": 0.15},
            )
            started = time.monotonic()
            try:
                response = await client.post(f"/approvals/{action}", json={"approved": True})
                assert time.monotonic() - started < 0.75
                assert response.status_code == 503
                assert response.json()["error"]["code"] == "DECISION_PENDING"
                assert not response.json()["error"]["retryable"]
            finally:
                release.set()
            await asyncio.wait_for(asyncio.gather(*runner.background_tasks), timeout=5)
            history = (await client.get(f"/conversations/{conversation}/messages")).json()
            assert history["active_run"] is None
            card = next(m["approval"] for m in history["messages"] if m["approval"])
            assert card["status"] == ("executed" if commit_first else "failed")
            with sessions() as session:
                assert session.scalar(
                    select(func.count())
                    .select_from(PasswordResetRequest)
                    .where(PasswordResetRequest.action_id == action)
                ) == int(commit_first)

    asyncio.run(run())


def test_cancelled_http_decision_preserves_committed_result(api):
    _, model, sessions, ids = api

    async def run():
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
        turns = TurnService(runner)
        app.dependency_overrides[get_turn_service] = lambda: turns
        original, entered, release = turns._decide, Event(), Event()

        def stalled_after_commit(*args):
            original(*args)
            entered.set()
            assert release.wait(timeout=5)

        turns._decide = stalled_after_commit
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/sessions", json={"customer_id": str(ids[0])})
            conversation = (await client.post("/conversations", json={})).json()["id"]
            model.replies.append(reset_call())
            pending = (
                await client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"})
            ).json()
            action = pending["pending_approval"]["action_id"]
            request = asyncio.create_task(
                client.post(f"/approvals/{action}", json={"approved": True})
            )
            try:
                assert await asyncio.to_thread(entered.wait, 5)
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
            finally:
                release.set()
            await asyncio.wait_for(asyncio.gather(*runner.background_tasks), timeout=5)
            history = (await client.get(f"/conversations/{conversation}/messages")).json()
            assert history["active_run"] is None
            assert history["messages"][1]["approval"]["status"] == "executed"
            with sessions() as session:
                assert (
                    session.scalar(
                        select(func.count())
                        .select_from(PasswordResetRequest)
                        .where(PasswordResetRequest.action_id == action)
                    )
                    == 1
                )

    asyncio.run(run())


def test_expired_decision_cleanup_does_not_block_http(api):
    _, model, sessions, ids = api

    async def run():
        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), model)
        app.dependency_overrides[get_turn_service] = lambda: TurnService(runner)
        original = runner.fail_pending_decision
        release = Event()

        def stalled_cleanup(*args):
            assert release.wait(timeout=5)
            return original(*args)

        runner.fail_pending_decision = stalled_cleanup
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/sessions", json={"customer_id": str(ids[0])})
            conversation = (await client.post("/conversations", json={})).json()["id"]
            model.replies.append(reset_call())
            pending = (
                await client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"})
            ).json()
            action = pending["pending_approval"]["action_id"]
            await runner._graph(ids[0], pending["run_id"]).aupdate_state(
                {"configurable": {"thread_id": pending["run_id"]}},
                {"remaining_seconds": 0.000001},
            )
            started = time.monotonic()
            try:
                response = await client.post(f"/approvals/{action}", json={"approved": True})
                assert time.monotonic() - started < 0.75
                assert response.status_code == 503
                assert response.json()["error"]["code"] == "DECISION_PENDING"
            finally:
                release.set()
            await asyncio.wait_for(asyncio.gather(*runner.background_tasks), timeout=5)
            history = (await client.get(f"/conversations/{conversation}/messages")).json()
            assert history["active_run"] is None
            assert history["messages"][1]["approval"]["status"] == "failed"

    asyncio.run(run())


def test_waiting_response_never_includes_another_runs_approval(api):
    client, model, _, ids = api
    login(client, ids[0])
    conversation = create(client)
    model.replies.append(reset_call())
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    turns = app.dependency_overrides[get_turn_service]()
    response = turns._response(
        ids[0],
        UUID(conversation),
        {
            "run_id": uuid4(),
            "status": "waiting_for_approval",
            "error": None,
        },
    )
    assert pending["pending_approval"] is not None
    assert response.pending_approval is None
    assert response.messages == []


def test_approval_revalidates_stored_payload(api):
    client, model, sessions, ids = api
    login(client, ids[0])
    conversation = create(client)
    model.replies.append(reset_call())
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    action_id = pending["pending_approval"]["action_id"]
    with sessions.begin() as session:
        action = session.get(ActionApproval, UUID(action_id))
        action.validated_payload = {
            **action.validated_payload,
            "account_display_name": "Not the owner",
        }
    response = client.post(f"/approvals/{action_id}", json={"approved": True})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_ACTION"
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.action_id == action_id)
            )
            == 0
        )
        assert session.get(ActionApproval, UUID(action_id)).status == "pending"


def test_http_failed_continuation_preserves_executed_card(api):
    client, model, sessions, ids = api
    login(client, ids[0])
    conversation = create(client)
    model.replies.extend([reset_call(), ValueError("provider failure")])
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    action = pending["pending_approval"]["action_id"]
    response = client.post(f"/approvals/{action}", json={"approved": True})
    assert response.status_code == 200
    turn = response.json()
    assert turn["status"] == "failed"
    card = next(message["approval"] for message in turn["messages"] if message["approval"])
    assert card["status"] == "executed" and card["result"]["simulated"]
    history = client.get(f"/conversations/{conversation}/messages").json()
    assert history["active_run"] is None
    assert history["messages"][1]["approval"]["result"] == card["result"]
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.action_id == action)
            )
            == 1
        )


def test_running_http_turn_rejects_concurrent_chat(api):
    _, _, sessions, ids = api

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        class BlockingModel:
            async def ainvoke(self, messages):
                entered.set()
                await release.wait()
                return AIMessage(content="Done.")

        runner = AgentTurns(sessions, get_settings(), InMemorySaver(), BlockingModel())
        app.dependency_overrides[get_turn_service] = lambda: TurnService(runner)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/sessions", json={"customer_id": str(ids[0])})
            conversation = (await client.post("/conversations", json={})).json()["id"]
            first = asyncio.create_task(
                client.post(f"/conversations/{conversation}/chat", json={"message": "first"})
            )
            await asyncio.wait_for(entered.wait(), timeout=5)
            duplicate = await client.post(
                f"/conversations/{conversation}/chat", json={"message": "second"}
            )
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "RUN_ACTIVE"
            release.set()
            assert (await first).json()["status"] == "completed"

    asyncio.run(run())


def test_concurrent_approval_decisions_execute_once(api):
    client, model, sessions, ids = api
    login(client, ids[0])
    conversation = create(client)
    model.replies.extend([reset_call(), AIMessage(content="Done.")])
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    action = pending["pending_approval"]["action_id"]
    barrier = Barrier(2)

    def decide():
        barrier.wait(timeout=5)
        return client.post(f"/approvals/{action}", json={"approved": True}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: decide(), range(2)))
    assert statuses == [200, 409]
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.action_id == action)
            )
            == 1
        )


def test_http_pending_survives_backend_restart(api, monkeypatch):
    _, model, sessions, ids = api
    monkeypatch.setattr("support_agent.main.get_engine", lambda: sessions.kw["bind"])
    app.dependency_overrides.pop(get_turn_service)
    model.replies.extend([reset_call(), AIMessage(content="Cancelled.")])
    with TestClient(app) as first:
        app.state.agent_turns.model = model
        login(first, ids[0])
        conversation = create(first)
        pending = first.post(
            f"/conversations/{conversation}/chat", json={"message": "Reset"}
        ).json()
        action_id, run_id = pending["pending_approval"]["action_id"], pending["run_id"]
    with TestClient(app) as second:
        app.state.agent_turns.model = model
        login(second, ids[0])
        history = second.get(f"/conversations/{conversation}/messages").json()
        assert history["pending_approval"]["action_id"] == action_id
        assert history["active_run"]["id"] == run_id
        result = second.post(f"/approvals/{action_id}", json={"approved": False})
        assert result.status_code == 200 and result.json()["status"] == "completed"
        second.portal.call(app.state.agent_turns.checkpointer.adelete_thread, run_id)


def test_restart_after_committed_decision_preserves_outcome_and_unlocks(api, monkeypatch):
    _, model, sessions, ids = api
    monkeypatch.setattr("support_agent.main.get_engine", lambda: sessions.kw["bind"])
    app.dependency_overrides.pop(get_turn_service)
    model.replies.append(reset_call())
    with TestClient(app) as first:
        app.state.agent_turns.model = model
        login(first, ids[0])
        conversation = create(first)
        pending = first.post(
            f"/conversations/{conversation}/chat", json={"message": "Reset"}
        ).json()
        action_id, run_id = pending["pending_approval"]["action_id"], pending["run_id"]
        # Simulate a crash after the transaction commits but before graph resume.
        TurnService(app.state.agent_turns)._decide(
            ids[0], UUID(run_id), UUID(action_id), True, time.monotonic() + 10
        )
    with TestClient(app) as second:
        login(second, ids[0])
        history = second.get(f"/conversations/{conversation}/messages").json()
        assert history["active_run"] is None
        card = next(message["approval"] for message in history["messages"] if message["approval"])
        assert card["status"] == "executed" and card["result"]["simulated"] is True
        assert second.post(f"/approvals/{action_id}", json={"approved": True}).status_code == 409
        with sessions() as session:
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(PasswordResetRequest)
                    .where(PasswordResetRequest.action_id == action_id)
                )
                == 1
            )
        model.replies.append(AIMessage(content="Ready."))
        app.state.agent_turns.model = model
        continuation = second.post(
            f"/conversations/{conversation}/chat", json={"message": "Continue"}
        ).json()
        assert continuation["status"] == "completed"
        for thread_id in (run_id, continuation["run_id"]):
            second.portal.call(app.state.agent_turns.checkpointer.adelete_thread, thread_id)


def test_http_pending_survives_checkpointer_reconnection(api):
    _, model, sessions, ids = api
    settings = get_settings().model_copy(update={"database_url": get_settings().test_database_url})
    model.replies.extend([reset_call(), AIMessage(content="Cancelled.")])

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            async with AsyncPostgresSaver.from_conn_string(
                settings.checkpointer_database_uri
            ) as saver:
                await saver.setup()
                app.dependency_overrides[get_turn_service] = lambda: TurnService(
                    AgentTurns(sessions, settings, saver, model)
                )
                assert (
                    await client.post("/sessions", json={"customer_id": str(ids[0])})
                ).status_code == 200
                conversation = (await client.post("/conversations", json={})).json()["id"]
                pending = (
                    await client.post(
                        f"/conversations/{conversation}/chat", json={"message": "Reset"}
                    )
                ).json()
                action = pending["pending_approval"]["action_id"]
                run_id = pending["run_id"]
            async with AsyncPostgresSaver.from_conn_string(
                settings.checkpointer_database_uri
            ) as saver:
                app.dependency_overrides[get_turn_service] = lambda: TurnService(
                    AgentTurns(sessions, settings, saver, model)
                )
                history = (await client.get(f"/conversations/{conversation}/messages")).json()
                assert history["pending_approval"]["action_id"] == action
                response = await client.post(f"/approvals/{action}", json={"approved": False})
                assert response.status_code == 200, response.text
                assert response.json()["status"] == "completed"
                await saver.adelete_thread(run_id)

    asyncio.run(run())


def test_http_reject_and_input_validation(api):
    client, model, sessions, ids = api
    login(client, ids[0])
    conversation = create(client)
    assert (
        client.post(f"/conversations/{conversation}/chat", json={"message": " "}).status_code == 422
    )
    assert (
        client.post(
            f"/conversations/{conversation}/chat", json={"message": "x", "run_id": str(uuid4())}
        ).status_code
        == 422
    )
    model.replies.extend([reset_call(), AIMessage(content="Cancelled.")])
    pending = client.post(f"/conversations/{conversation}/chat", json={"message": "Reset"}).json()
    action = pending["pending_approval"]["action_id"]
    assert client.post(f"/approvals/{action}", json={"approved": 1}).status_code == 422
    response = client.post(f"/approvals/{action}", json={"approved": False})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    assert response.json()["messages"][1]["approval"]["status"] == "rejected"
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PasswordResetRequest)
                .where(PasswordResetRequest.action_id == action)
            )
            == 0
        )
