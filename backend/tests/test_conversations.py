from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from scripts.seed_data import seed_demo_data
from support_agent.core.config import get_settings
from support_agent.core.database import get_db_session
from support_agent.core.schema import initialize_schema
from support_agent.main import app
from support_agent.models import ActionApproval, AgentRun, Conversation, Customer
from support_agent.repositories.conversations import recover_running_runs
from support_agent.schemas.account import ResetPayload
from support_agent.schemas.conversation import Citation
from support_agent.services.conversations import ConversationError, ConversationService


@pytest.fixture
def environment() -> Iterator[tuple[TestClient, Session]]:
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    seed_demo_data(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")

        def db():
            try:
                yield session
            except Exception:
                session.rollback()
                raise

        app.dependency_overrides[get_db_session] = db
        client = TestClient(app)
        yield client, session
        client.close()
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
    engine.dispose()


def test_history_feedback_and_ownership(environment) -> None:
    client, session = environment
    alex = session.scalar(select(Customer).where(Customer.handle == "alex"))
    taylor = session.scalar(select(Customer).where(Customer.handle == "taylor"))
    assert client.get("/conversations").status_code == 401
    client.post("/sessions", json={"customer_id": str(alex.id)})
    created = client.post("/conversations", json={})
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    conversation = session.get(Conversation, conversation_id)
    service = ConversationService(session)
    run = service.reserve_run(alex.id, conversation.id)
    user_id = service.add_message(alex.id, run.id, "user", "Question")
    source = Citation(article_id=uuid4(), chunk_id=uuid4(), article_title="Policy", section="Terms")
    fake = Citation(article_id=uuid4(), chunk_id=uuid4(), article_title="Fake", section="Fake")
    assistant_id = service.add_message(
        alex.id, run.id, "assistant", "Answer", citations=[source, fake], retrieved=[source]
    )
    action_id = uuid4()
    payload = ResetPayload(action_id=action_id, account_display_name=alex.display_name)
    action = ActionApproval(
        id=action_id,
        run_id=run.id,
        action_type="request_password_reset",
        status="pending",
        validated_payload=payload.model_dump(mode="json"),
    )
    session.add(action)
    session.flush()
    service.add_message(alex.id, run.id, "action", None, approval_id=action_id)
    service.set_run_status(alex.id, run.id, "waiting_for_approval")
    session.commit()
    session.expire_all()
    history = client.get(f"/conversations/{conversation_id}/messages").json()
    assert [message["role"] for message in history["messages"]] == ["user", "assistant", "action"]
    assert len(history["messages"][1]["citations"]) == 1
    assert history["pending_approval"]["action_id"] == str(action_id)
    assert history["active_run"]["status"] == "waiting_for_approval"
    assert (
        client.put(f"/messages/{user_id}/feedback", json={"rating": "positive"}).status_code == 422
    )
    assert (
        client.put(f"/messages/{assistant_id}/feedback", json={"rating": "positive"}).status_code
        == 200
    )
    assert (
        client.put(
            f"/messages/{assistant_id}/feedback", json={"rating": "negative", "comment": "No"}
        ).status_code
        == 200
    )
    history = client.get(f"/conversations/{conversation_id}/messages").json()
    assert history["messages"][1]["feedback"]["rating"] == "negative"
    client.post("/sessions", json={"customer_id": str(taylor.id)})
    assert client.get(f"/conversations/{conversation_id}/messages").status_code == 404
    assert (
        client.put(f"/messages/{assistant_id}/feedback", json={"rating": "positive"}).status_code
        == 404
    )
    assert client.get("/conversations").json()["items"] == []


def test_recovery_keeps_waiting_and_releases_running(environment) -> None:
    _, session = environment
    alex = session.scalar(select(Customer).where(Customer.handle == "alex"))
    service = ConversationService(session)
    first = service.create(alex.id, "First")
    second = service.create(alex.id, "Second")
    running = service.reserve_run(alex.id, first.id)
    waiting = service.reserve_run(alex.id, second.id)
    service.set_run_status(alex.id, waiting.id, "waiting_for_approval")
    assert recover_running_runs(session) >= 1
    session.expire_all()
    assert session.get(AgentRun, running.id).status == "failed"
    assert session.get(AgentRun, waiting.id).status == "waiting_for_approval"
    assert service.reserve_run(alex.id, first.id).status == "running"
    with pytest.raises(ConversationError, match="Finish"):
        service.reserve_run(alex.id, second.id)


def test_startup_recovers_committed_running_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    customer_id, first_id, second_id = uuid4(), uuid4(), uuid4()
    running_id, waiting_id = uuid4(), uuid4()
    with Session(engine) as session, session.begin():
        session.add(Customer(id=customer_id, handle=f"test-{uuid4()}", display_name="Test"))
        session.flush()
        session.add_all(
            [
                Conversation(id=first_id, customer_id=customer_id, title="First"),
                Conversation(id=second_id, customer_id=customer_id, title="Second"),
            ]
        )
        session.flush()
        session.add_all(
            [
                AgentRun(id=running_id, conversation_id=first_id, status="running"),
                AgentRun(id=waiting_id, conversation_id=second_id, status="waiting_for_approval"),
            ]
        )
        session.flush()
        action_id = uuid4()
        request_id = uuid4()
        session.add(
            ActionApproval(
                id=action_id,
                run_id=running_id,
                action_type="request_password_reset",
                status="executed",
                validated_payload=ResetPayload(
                    action_id=action_id, account_display_name="Test"
                ).model_dump(mode="json"),
                execution_result={
                    "request_id": str(request_id),
                    "status": "requested",
                    "reset_url": f"https://example.invalid/reset/{request_id}",
                    "simulated": True,
                },
            )
        )
    monkeypatch.setattr("support_agent.main.get_engine", lambda: engine)
    try:
        with TestClient(app) as client:
            assert client.get("/health").status_code == 200
        with Session(engine) as session:
            assert session.get(AgentRun, running_id).status == "failed"
            assert session.get(AgentRun, waiting_id).status == "waiting_for_approval"
            assert session.get(ActionApproval, action_id).execution_result["request_id"] == str(
                request_id
            )
            ConversationService(session).reserve_run(customer_id, first_id)
            session.rollback()
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Customer).where(Customer.id == customer_id))
        engine.dispose()


def test_concurrent_run_reservation() -> None:
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    customer_id = uuid4()
    conversation_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(Customer(id=customer_id, handle=f"test-{uuid4()}", display_name="Test"))
        session.flush()
        session.add(Conversation(id=conversation_id, customer_id=customer_id, title="Test"))
    barrier = Barrier(2)

    def reserve():
        with Session(engine) as session:
            barrier.wait(timeout=10)
            try:
                ConversationService(session).reserve_run(customer_id, conversation_id)
                session.commit()
                return "created"
            except ConversationError as exc:
                session.rollback()
                return exc.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(lambda _: reserve(), range(2))) == ["RUN_ACTIVE", "created"]
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(Customer).where(Customer.id == customer_id))
        engine.dispose()
