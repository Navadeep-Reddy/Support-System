from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from support_agent.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class Conversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "conversations"

    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="New conversation")

    __table_args__ = (
        Index("ix_conversations_customer_updated", "customer_id", "updated_at"),
    )


class Message(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("agent_runs.id", ondelete="SET NULL"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    approval_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("action_approvals.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant', 'action')", name="ck_messages_role"),
        CheckConstraint(
            "(role = 'action' AND approval_id IS NOT NULL AND content IS NULL) OR "
            "(role IN ('user', 'assistant') AND content IS NOT NULL AND approval_id IS NULL)",
            name="ck_messages_action_card_shape",
        ),
        Index("ix_messages_conversation_created", "conversation_id", "created_at", "id"),
    )


class Feedback(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "feedback"

    message_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[str] = mapped_column(String(12), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("rating IN ('positive', 'negative')", name="ck_feedback_rating"),
        Index("uq_feedback_customer_message", "customer_id", "message_id", unique=True),
    )
