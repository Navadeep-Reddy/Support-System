from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from scripts.seed_data import seed_demo_data
from support_agent.core.config import get_settings
from support_agent.core.schema import initialize_schema
from support_agent.models import (
    ActionApproval,
    AgentRun,
    Conversation,
    Customer,
    PasswordResetRequest,
    Payment,
    Plan,
    Subscription,
)
from support_agent.services.accounts import AccountError, AccountService


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection) as session:
            yield session
        transaction.rollback()
    engine.dispose()


def setup_customer(session: Session, name: str) -> Customer:
    customer = Customer(id=uuid4(), handle=f"test-{uuid4()}", display_name=name)
    session.add(customer)
    session.flush()
    return customer


def make_action(session: Session, customer: Customer, status: str = "pending") -> ActionApproval:
    conversation = Conversation(customer_id=customer.id, title="Test")
    session.add(conversation)
    session.flush()
    run = AgentRun(conversation_id=conversation.id, status="waiting_for_approval")
    session.add(run)
    session.flush()
    action_id = uuid4()
    payload = AccountService(session).prepare_reset(customer.id, action_id)
    action = ActionApproval(
        id=action_id, run_id=run.id, action_type="request_password_reset", status=status,
        decided_at=datetime.now(UTC) if status != "pending" else None,
        validated_payload=payload.model_dump(mode="json"),
    )
    session.add(action)
    session.flush()
    return action


def test_customer_scoped_lookups_and_stable_payment_order(session: Session) -> None:
    alex = setup_customer(session, "Alex")
    taylor = setup_customer(session, "Taylor")
    plan = Plan(plan_code=f"test-{uuid4().hex[:20]}", name="Pro", monthly_price=Decimal("15.00"),
                currency="USD")
    session.add(plan)
    session.flush()
    session.add(Subscription(customer_id=alex.id, plan_id=plan.id, status="active"))
    timestamp = datetime.now(UTC)
    for payment_id, amount in [(UUID(int=1), "10.00"), (UUID(int=2), "15.00")]:
        session.add(Payment(id=payment_id, customer_id=alex.id, amount=Decimal(amount),
                            currency="USD", occurred_at=timestamp, status="successful",
                            payment_type="initial"))
    session.flush()
    service = AccountService(session)
    assert service.current_subscription(alex.id).model_dump(mode="json")["monthly_price"] == "15.00"
    assert service.latest_payment(alex.id).amount == Decimal("15.00")
    for method, code in [(service.current_subscription, "SUBSCRIPTION_NOT_FOUND"),
                         (service.latest_payment, "PAYMENT_NOT_FOUND")]:
        with pytest.raises(AccountError) as error:
            method(taylor.id)
        assert error.value.code == code


def test_reset_requires_owned_approval_and_is_idempotent(session: Session) -> None:
    alex = setup_customer(session, "Alex")
    taylor = setup_customer(session, "Taylor")
    service = AccountService(session)
    action = make_action(session, alex)
    assert session.scalar(select(func.count()).select_from(PasswordResetRequest).where(
        PasswordResetRequest.action_id == action.id)) == 0
    for customer, status, code in [(alex, "pending", "APPROVAL_REQUIRED"),
                                   (alex, "rejected", "APPROVAL_REQUIRED"),
                                   (taylor, "approved", "NOT_FOUND")]:
        action.status = status
        action.decided_at = datetime.now(UTC) if status != "pending" else None
        session.flush()
        with pytest.raises(AccountError) as error:
            service.execute_reset(customer.id, action.id)
        assert error.value.code == code
    action.status = "approved"
    action.decided_at = datetime.now(UTC)
    session.flush()
    result = service.execute_reset(alex.id, action.id)
    assert result.simulated and result.reset_url == f"https://example.invalid/reset/{result.request_id}"
    assert service.execute_reset(alex.id, action.id) == result
    assert action.status == "executed"
    assert session.scalar(select(func.count()).select_from(PasswordResetRequest).where(
        PasswordResetRequest.action_id == action.id)) == 1


def test_seeded_profiles_return_distinct_account_data() -> None:
    engine = create_engine(get_settings().test_database_url)
    try:
        seed_demo_data(engine)
        with Session(engine) as session:
            service = AccountService(session)
            alex = session.scalar(select(Customer).where(Customer.handle == "alex"))
            taylor = session.scalar(select(Customer).where(Customer.handle == "taylor"))
            assert alex is not None and taylor is not None
            assert service.current_subscription(alex.id).plan == "Pro"
            assert service.current_subscription(alex.id).monthly_price == Decimal("15.00")
            assert service.current_subscription(taylor.id).plan == "Business"
            assert service.current_subscription(taylor.id).monthly_price == Decimal("39.00")
            assert service.latest_payment(alex.id).status == "successful"
            assert service.latest_payment(taylor.id).failure_reason == "insufficient funds"
    finally:
        engine.dispose()


def test_reset_and_approval_result_roll_back_together(session: Session) -> None:
    customer = setup_customer(session, "Alex")
    action = make_action(session, customer, "approved")
    savepoint = session.begin_nested()
    AccountService(session).execute_reset(customer.id, action.id)
    savepoint.rollback()
    session.refresh(action)
    assert action.status == "approved"
    assert action.execution_result is None
    assert session.scalar(select(func.count()).select_from(PasswordResetRequest).where(
        PasswordResetRequest.action_id == action.id)) == 0


def test_reset_rejects_changed_payload(session: Session) -> None:
    customer = setup_customer(session, "Alex")
    action = make_action(session, customer, "approved")
    action.validated_payload = {**action.validated_payload, "action_id": str(uuid4())}
    session.flush()
    with pytest.raises(AccountError) as error:
        AccountService(session).execute_reset(customer.id, action.id)
    assert error.value.code == "INVALID_ACTION"
    assert session.scalar(select(func.count()).select_from(PasswordResetRequest).where(
        PasswordResetRequest.action_id == action.id)) == 0
