from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from support_agent.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Plan(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "plans"

    plan_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    monthly_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    __table_args__ = (
        CheckConstraint("monthly_price >= 0", name="ck_plans_nonnegative_monthly_price"),
        CheckConstraint("length(currency) = 3", name="ck_plans_currency_length"),
    )


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    plan_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("plans.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    billing_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    billing_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'past_due', 'cancelled', 'expired')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint(
            "billing_period_end IS NULL OR billing_period_start IS NULL "
            "OR billing_period_end > billing_period_start",
            name="ck_subscriptions_billing_period_order",
        ),
    )


class Payment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "payments"

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    payment_type: Mapped[str] = mapped_column(String(24), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(240))

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_payments_nonnegative_amount"),
        CheckConstraint("length(currency) = 3", name="ck_payments_currency_length"),
        CheckConstraint(
            "status IN ('successful', 'failed', 'refunded', 'refund_requested')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "payment_type IN ('initial', 'renewal')", name="ck_payments_type"
        ),
        Index("ix_payments_customer_latest", "customer_id", "occurred_at", "id"),
    )
