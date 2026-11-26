from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from support_agent.models import KnowledgeArticle, KnowledgeChunk


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_articles(self) -> list[KnowledgeArticle]:
        return list(
            self.session.scalars(
                select(KnowledgeArticle).order_by(KnowledgeArticle.title, KnowledgeArticle.id)
            )
        )

    def get(self, article_id: UUID) -> KnowledgeArticle | None:
        return self.session.get(KnowledgeArticle, article_id)

    def replace_chunks(self, article_id: UUID, chunks: list[KnowledgeChunk]) -> None:
        self.session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))
        self.session.add_all(chunks)

    def search(self, vector: list[float], threshold: float, limit: int):
        distance = KnowledgeChunk.embedding.cosine_distance(vector)
        return self.session.execute(
            select(KnowledgeChunk, KnowledgeArticle, (1 - distance).label("score"))
            .join(KnowledgeArticle, KnowledgeChunk.article_id == KnowledgeArticle.id)
            .where(1 - distance >= threshold)
            .order_by(distance, KnowledgeChunk.id)
            .limit(limit)
        ).all()
