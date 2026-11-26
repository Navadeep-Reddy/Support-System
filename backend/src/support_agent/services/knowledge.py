import logging
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from support_agent.core.config import get_settings
from support_agent.models import KnowledgeArticle, KnowledgeChunk
from support_agent.repositories.knowledge import KnowledgeRepository
from support_agent.schemas.knowledge import Article, ArticleInput, ArticleSummary, RetrievedChunk
from support_agent.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Section:
    heading: str
    path: str
    text: str


def split_sections(body: str) -> list[Section]:
    sections: list[Section] = []
    headings: list[tuple[int, str]] = []
    lines: list[str] = []
    fence: tuple[str, int] | None = None

    def flush() -> None:
        text = "\n".join(lines).strip()
        if text:
            path = " > ".join(heading for _, heading in headings) or "Introduction"
            heading = headings[-1][1] if headings else "Introduction"
            if len(heading) > 240 or len(path) > 1000:
                raise KnowledgeError("VALIDATION_ERROR", "A section heading is too long.")
            sections.append(Section(heading, path, text))
        lines.clear()

    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = (value[0], len(value))
            elif value[0] == fence[0] and len(value) >= fence[1]:
                fence = None
            lines.append(line)
            continue
        match = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line) if fence is None else None
        if match:
            flush()
            level, heading = len(match.group(1)), match.group(2).strip()
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, heading))
        else:
            lines.append(line)
    flush()
    if not sections:
        raise KnowledgeError("VALIDATION_ERROR", "The article must contain section text.")
    return sections


def embedding_text(article: ArticleInput, section: Section) -> str:
    return (
        f"Title: {article.title}\nCategory: {article.category}\n"
        f"Section: {section.path}\n{section.text}"
    )


class KnowledgeService:
    def __init__(self, session: Session, embeddings: EmbeddingService) -> None:
        self.session = session
        self.repository = KnowledgeRepository(session)
        self.embeddings = embeddings

    def list_articles(self) -> list[ArticleSummary]:
        return [ArticleSummary.model_validate(item) for item in self.repository.list_articles()]

    def get(self, article_id: UUID) -> Article:
        article = self.repository.get(article_id)
        if article is None:
            raise KnowledgeError("NOT_FOUND", "The article was not found.")
        return Article.model_validate(article)

    def save(self, data: ArticleInput, article_id: UUID | None = None) -> Article:
        article = self.repository.get(article_id) if article_id else None
        if article_id and article is None:
            raise KnowledgeError("NOT_FOUND", "The article was not found.")
        sections = split_sections(data.body)
        texts = [embedding_text(data, section) for section in sections]
        # UTF-8 byte count is a conservative token upper bound without a model tokenizer.
        if any(len(text.encode("utf-8")) > 512 for text in texts):
            raise KnowledgeError("SECTION_TOO_LARGE", "A section exceeds the indexing limit.")
        try:
            vectors = self.embeddings.embed_passages(texts)
            if len(vectors) != len(sections):
                raise ValueError("Embedding count mismatch")
        except Exception as exc:
            logger.warning("knowledge_indexing_failed")
            raise KnowledgeError(
                "PROVIDER_UNAVAILABLE", "Article indexing is unavailable."
            ) from exc
        if article is None:
            article = KnowledgeArticle(title=data.title, category=data.category, body=data.body)
            self.session.add(article)
            self.session.flush()
        else:
            article.title, article.category, article.body = data.title, data.category, data.body
        chunks = [
            KnowledgeChunk(
                article_id=article.id,
                heading=section.heading,
                heading_path=section.path,
                section_order=index,
                source_text=section.text,
                embedding=vector,
            )
            for index, (section, vector) in enumerate(zip(sections, vectors, strict=True))
        ]
        self.repository.replace_chunks(article.id, chunks)
        self.session.flush()
        return Article.model_validate(article)

    def delete(self, article_id: UUID) -> None:
        article = self.repository.get(article_id)
        if article is None:
            raise KnowledgeError("NOT_FOUND", "The article was not found.")
        self.session.delete(article)
        self.session.flush()

    def search(self, query: str) -> list[RetrievedChunk]:
        query = query.strip()
        if not query:
            raise KnowledgeError("VALIDATION_ERROR", "The search query must not be blank.")
        try:
            vector = self.embeddings.embed_query(query)
        except Exception as exc:
            logger.warning("knowledge_query_embedding_failed")
            raise KnowledgeError(
                "PROVIDER_UNAVAILABLE", "Knowledge search is unavailable."
            ) from exc
        settings = get_settings()
        rows = self.repository.search(
            vector, settings.retrieval_min_similarity, settings.retrieval_top_k
        )
        return [
            RetrievedChunk(
                article_id=article.id,
                chunk_id=chunk.id,
                article_title=article.title,
                section=chunk.heading_path,
                category=article.category,
                text=chunk.source_text,
                score=float(score),
            )
            for chunk, article, score in rows
        ]
