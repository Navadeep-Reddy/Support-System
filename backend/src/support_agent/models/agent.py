from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from support_agent.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"

    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'waiting_for_approval', 'completed', 'failed')",
            name="ck_agent_runs_status",
        ),
        Index(
            "uq_agent_runs_one_active_per_conversation",
            "conversation_id",
            unique=True,
            postgresql_where=text("status IN ('running', 'waiting_for_approval')"),
        ),
    )


class ActionApproval(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "action_approvals"

    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    validated_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_result: Mapped[dict[str, object] | None] = mapped_column(JSONB)

    __table_args__ = (
        CheckConstraint(
            "action_type IN ('request_password_reset')", name="ck_action_approvals_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'executed', 'failed')",
            name="ck_action_approvals_status",
        ),
        Index(
            "uq_action_approvals_one_pending_per_run",
            "run_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_action_approvals_status_created", "status", "created_at"),
    )


class PasswordResetRequest(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "password_reset_requests"

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    action_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("action_approvals.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="requested")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("status = 'requested'", name="ck_password_reset_requests_status"),
        Index("ix_password_reset_requests_customer_created", "customer_id", "created_at"),
    )
