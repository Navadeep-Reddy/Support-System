from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from support_agent.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

EMBEDDING_DIMENSIONS = 2048


class KnowledgeArticle(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_articles"

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_knowledge_articles_title_nonblank"),
        CheckConstraint(
            "length(trim(category)) > 0", name="ck_knowledge_articles_category_nonblank"
        ),
        CheckConstraint("length(trim(body)) > 0", name="ck_knowledge_articles_body_nonblank"),
    )


class KnowledgeChunk(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "knowledge_chunks"

    article_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_articles.id", ondelete="CASCADE"), nullable=False
    )
    heading: Mapped[str] = mapped_column(String(240), nullable=False)
    heading_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("section_order >= 0", name="ck_knowledge_chunks_nonnegative_order"),
        UniqueConstraint("article_id", "section_order", name="uq_knowledge_chunks_article_order"),
        Index("ix_knowledge_chunks_article", "article_id"),
    )
