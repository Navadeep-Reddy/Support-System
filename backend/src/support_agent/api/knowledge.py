from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from support_agent.api.sessions import Database, KnowledgeSession, current_knowledge_admin
from support_agent.repositories.knowledge import KnowledgeRepository
from support_agent.schemas.knowledge import Article, ArticleInput, ArticleList, ArticleSummary
from support_agent.services.embeddings import EmbeddingService
from support_agent.services.knowledge import KnowledgeError, KnowledgeService

router = APIRouter(prefix="/knowledge/articles", tags=["knowledge"])
Admin = Annotated[KnowledgeSession, Depends(current_knowledge_admin)]


def get_embeddings() -> EmbeddingService:
    try:
        return EmbeddingService()
    except Exception as exc:
        raise KnowledgeError("PROVIDER_UNAVAILABLE", "Article indexing is unavailable.") from exc


@router.get("", response_model=ArticleList)
def list_articles(db: Database, _admin: Admin) -> ArticleList:
    return ArticleList(
        items=[
            ArticleSummary.model_validate(article)
            for article in KnowledgeRepository(db).list_articles()
        ]
    )


@router.get("/{article_id}", response_model=Article)
def get_article(article_id: UUID, db: Database, _admin: Admin) -> Article:
    article = KnowledgeRepository(db).get(article_id)
    if article is None:
        raise KnowledgeError("NOT_FOUND", "The article was not found.")
    return Article.model_validate(article)


@router.post("", response_model=Article, status_code=201)
def create_article(
    data: ArticleInput,
    db: Database,
    _admin: Admin,
    embeddings: Annotated[EmbeddingService, Depends(get_embeddings)],
) -> Article:
    article = KnowledgeService(db, embeddings).save(data)
    db.commit()
    return article


@router.put("/{article_id}", response_model=Article)
def update_article(
    article_id: UUID,
    data: ArticleInput,
    db: Database,
    _admin: Admin,
    embeddings: Annotated[EmbeddingService, Depends(get_embeddings)],
) -> Article:
    article = KnowledgeService(db, embeddings).save(data, article_id)
    db.commit()
    return article


@router.delete("/{article_id}", status_code=204)
def delete_article(article_id: UUID, db: Database, _admin: Admin) -> Response:
    article = KnowledgeRepository(db).get(article_id)
    if article is None:
        raise KnowledgeError("NOT_FOUND", "The article was not found.")
    db.delete(article)
    db.commit()
    return Response(status_code=204)
