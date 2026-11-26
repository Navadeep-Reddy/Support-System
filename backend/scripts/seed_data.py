"""Idempotently seed local demo plans, customers, subscriptions, and sample payments."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from support_agent.core.database import get_engine
from support_agent.core.schema import initialize_schema
from support_agent.models import Customer, Payment, Plan, Subscription


def stable_id(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"aatra-support-demo/{key}")


def seed_demo_data(engine: Engine | None = None, *, refresh_existing: bool = True) -> None:
    engine = engine or get_engine()
    initialize_schema(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(UTC)
    plans_by_code: dict[str, Plan] = {}
    customers_by_handle: dict[str, Customer] = {}

    with session_factory.begin() as session:
        plan_seeds = (
            ("free", "Free", Decimal("0.00")),
            ("pro", "Pro", Decimal("15.00")),
            ("business", "Business", Decimal("39.00")),
        )
        for code, name, price in plan_seeds:
            plan = session.scalar(select(Plan).where(Plan.plan_code == code))
            if plan is None:
                plan = Plan(
                    id=stable_id(f"plan/{code}"),
                    plan_code=code,
                    name=name,
                    monthly_price=price,
                )
                session.add(plan)
            elif refresh_existing:
                plan.name = name
                plan.monthly_price = price
                plan.currency = "USD"
            plans_by_code[code] = plan

        customer_seeds = (
            ("alex", "Alex"),
            ("taylor", "Taylor"),
            ("maya", "Maya"),
            ("jordan", "Jordan"),
            ("riley", "Riley"),
            ("morgan", "Morgan"),
        )
        for handle, display_name in customer_seeds:
            customer = session.scalar(select(Customer).where(Customer.handle == handle))
            if customer is None:
                # Preserve IDs and related records from earlier seed runs.
                legacy_handle = f"{handle}-demo"
                customer = session.scalar(select(Customer).where(Customer.handle == legacy_handle))
            if customer is None:
                customer = Customer(
                    id=stable_id(f"customer/{handle}"),
                    handle=handle,
                    display_name=display_name,
                )
                session.add(customer)
            elif refresh_existing:
                customer.handle = handle
                customer.display_name = display_name
            customers_by_handle[handle] = customer

        subscription_seeds = (
            ("alex", "pro"),
            ("taylor", "business"),
            ("maya", "pro"),
            ("jordan", "business"),
            ("riley", "free"),
            ("morgan", "pro"),
        )
        for handle, plan_code in subscription_seeds:
            customer = customers_by_handle[handle]
            subscription = session.scalar(
                select(Subscription).where(Subscription.customer_id == customer.id)
            )
            if subscription is None:
                subscription = Subscription(
                    id=stable_id(f"subscription/{handle}"), customer_id=customer.id
                )
                session.add(subscription)
            elif not refresh_existing:
                continue
            subscription.plan_id = plans_by_code[plan_code].id
            subscription.status = "active"
            subscription.billing_period_start = now - timedelta(days=15)
            subscription.billing_period_end = now + timedelta(days=15)

        payment_seeds = (
            {
                "key": "payment/alex-initial",
                "handle": "alex",
                "amount": Decimal("15.00"),
                "occurred_at": now - timedelta(days=5),
                "status": "successful",
                "payment_type": "initial",
                "failure_reason": None,
            },
            {
                "key": "payment/taylor-renewal",
                "handle": "taylor",
                "amount": Decimal("39.00"),
                "occurred_at": now - timedelta(days=1),
                "status": "failed",
                "payment_type": "renewal",
                "failure_reason": "insufficient funds",
            },
            {
                "key": "payment/maya-initial",
                "handle": "maya",
                "amount": Decimal("15.00"),
                "occurred_at": now - timedelta(days=3),
                "status": "successful",
                "payment_type": "initial",
                "failure_reason": None,
            },
            {
                "key": "payment/jordan-renewal",
                "handle": "jordan",
                "amount": Decimal("39.00"),
                "occurred_at": now - timedelta(days=2),
                "status": "failed",
                "payment_type": "renewal",
                "failure_reason": "expired card",
            },
            {
                "key": "payment/morgan-renewal",
                "handle": "morgan",
                "amount": Decimal("15.00"),
                "occurred_at": now - timedelta(days=4),
                "status": "successful",
                "payment_type": "renewal",
                "failure_reason": None,
            },
        )
        for seed in payment_seeds:
            payment_id = stable_id(seed["key"])
            payment = session.get(Payment, payment_id)
            if payment is None:
                payment = Payment(id=payment_id, customer_id=customers_by_handle[seed["handle"]].id)
                session.add(payment)
            elif not refresh_existing:
                continue
            payment.amount = seed["amount"]
            payment.currency = "USD"
            payment.occurred_at = seed["occurred_at"]
            payment.status = seed["status"]
            payment.payment_type = seed["payment_type"]
            payment.failure_reason = seed["failure_reason"]

    print("Seeded 3 plans, 6 customers, 6 subscriptions, and 5 sample payments.")


def main() -> None:
    seed_demo_data()


if __name__ == "__main__":
    main()
