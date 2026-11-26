from collections.abc import Iterator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from scripts.seed_data import seed_demo_data
from support_agent.core.config import get_settings
from support_agent.core.schema import initialize_schema
from support_agent.models import Base, Customer, Payment, Plan, Subscription


@pytest.fixture(scope="module")
def test_engine() -> Iterator[Engine]:
    # Test fixtures must never use DATABASE_URL or modify the demo database.
    engine = create_engine(get_settings().test_database_url, pool_pre_ping=True)
    initialize_schema(engine)
    yield engine
    engine.dispose()


def test_application_model_registry_and_constraints(test_engine: Engine) -> None:
    expected_tables = {
        "customers",
        "plans",
        "subscriptions",
        "payments",
        "password_reset_requests",
        "knowledge_articles",
        "knowledge_chunks",
        "conversations",
        "messages",
        "feedback",
        "agent_runs",
        "action_approvals",
    }
    assert set(Base.metadata.tables) == expected_tables

    inspector = inspect(test_engine)
    for table_name in expected_tables:
        assert table_name in inspector.get_table_names()

    run_indexes = {
        index["name"]: index for index in inspector.get_indexes("agent_runs")
    }
    approval_indexes = {
        index["name"]: index for index in inspector.get_indexes("action_approvals")
    }
    assert "uq_agent_runs_one_active_per_conversation" in run_indexes
    run_predicate = run_indexes["uq_agent_runs_one_active_per_conversation"][
        "dialect_options"
    ]["postgresql_where"]
    assert "running" in run_predicate and "waiting_for_approval" in run_predicate
    assert "uq_action_approvals_one_pending_per_run" in approval_indexes
    pending_predicate = approval_indexes["uq_action_approvals_one_pending_per_run"][
        "dialect_options"
    ]["postgresql_where"]
    assert "pending" in pending_predicate

    subscription_unique = inspector.get_unique_constraints("subscriptions")
    assert any(item["column_names"] == ["customer_id"] for item in subscription_unique)
    reset_unique_indexes = inspector.get_indexes("password_reset_requests")
    assert any(
        index["unique"] and index["column_names"] == ["action_id"]
        for index in reset_unique_indexes
    )
    feedback_indexes = inspector.get_indexes("feedback")
    assert any(
        index["unique"] and set(index["column_names"]) == {"customer_id", "message_id"}
        for index in feedback_indexes
    )

    vector_type = test_engine.connect().execute(
        text(
            "SELECT format_type(a.atttypid, a.atttypmod) "
            "FROM pg_attribute a "
            "WHERE a.attrelid = 'knowledge_chunks'::regclass AND a.attname = 'embedding'"
        )
    ).scalar_one()
    assert vector_type == "vector(2048)"


def test_demo_seed_is_repeatable_without_duplicates(test_engine: Engine) -> None:
    seed_demo_data(test_engine)
    seed_demo_data(test_engine)

    session_factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Plan)) == 3
        assert session.scalar(select(func.count()).select_from(Customer)) == 2
        assert session.scalar(select(func.count()).select_from(Subscription)) == 2
        assert session.scalar(select(func.count()).select_from(Payment)) == 2

        plans = dict(session.execute(select(Plan.plan_code, Plan.monthly_price)).all())
        assert plans == {
            "free": Decimal("0.00"),
            "pro": Decimal("15.00"),
            "business": Decimal("39.00"),
        }

        customers = {customer.handle: customer for customer in session.scalars(select(Customer))}
        assert set(customers) == {"alex", "taylor"}
        subscriptions = list(
            session.execute(
                select(Customer.handle, Plan.plan_code, Subscription.status)
                .join(Subscription, Subscription.customer_id == Customer.id)
                .join(Plan, Plan.id == Subscription.plan_id)
            )
        )
        assert set(subscriptions) == {
            ("alex", "pro", "active"),
            ("taylor", "business", "active"),
        }

        payments = list(session.scalars(select(Payment)))
        assert {
            (
                payment.customer_id,
                payment.amount,
                payment.status,
                payment.payment_type,
                payment.failure_reason,
            )
            for payment in payments
        } == {
            (customers["alex"].id, Decimal("15.00"), "successful", "initial", None),
            (
                customers["taylor"].id,
                Decimal("39.00"),
                "failed",
                "renewal",
                "insufficient funds",
            ),
        }
