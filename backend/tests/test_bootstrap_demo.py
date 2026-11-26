from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import Session

from scripts import bootstrap_demo
from support_agent.core.config import get_settings
from support_agent.core.schema import initialize_schema
from support_agent.models import KnowledgeArticle, KnowledgeChunk


class FlakyEmbeddings:
    def __init__(self, failures=0):
        self.failures = failures
        self.calls = 0

    def embed_passages(self, texts):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary provider failure")
        return [[1.0] + [0.0] * 2047 for _ in texts]


@pytest.fixture
def isolated_articles(monkeypatch):
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    prefix = f"Test bootstrap {uuid4()}"
    articles = (
        (f"{prefix} one", "test", "## Section\nFirst"),
        (f"{prefix} two", "test", "## Section\nSecond"),
    )
    monkeypatch.setattr(bootstrap_demo, "ARTICLES", articles)
    yield engine, articles
    with Session(engine) as session, session.begin():
        session.execute(delete(KnowledgeArticle).where(KnowledgeArticle.title.like(f"{prefix}%")))
    engine.dispose()


def test_seeding_retries_and_commits_each_article(isolated_articles):
    engine, articles = isolated_articles
    embeddings = FlakyEmbeddings(failures=3)
    sleeps = []
    bootstrap_demo.seed_articles_with_retry(engine, embeddings, sleep=sleeps.append)
    bootstrap_demo.seed_articles_with_retry(engine, embeddings, sleep=sleeps.append)
    assert sleeps == [1, 2, 4]
    assert embeddings.calls == 5
    with Session(engine) as session:
        ids = list(
            session.scalars(
                select(KnowledgeArticle.id).where(
                    KnowledgeArticle.title.in_([item[0] for item in articles])
                )
            )
        )
        assert len(ids) == 2
        assert (
            session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.article_id.in_(ids))
            )
            == 2
        )


def test_interrupted_indexing_resumes_without_reindexing_committed_articles(isolated_articles):
    engine, articles = isolated_articles

    class InterruptSecond(FlakyEmbeddings):
        def embed_passages(self, texts):
            if self.calls == 1:
                raise RuntimeError("provider unavailable")
            return super().embed_passages(texts)

    def interrupt(_delay):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        bootstrap_demo.seed_articles_with_retry(engine, InterruptSecond(), sleep=interrupt)
    with Session(engine) as session:
        assert session.scalar(
            select(KnowledgeArticle.id).where(KnowledgeArticle.title == articles[0][0])
        )
        assert (
            session.scalar(
                select(KnowledgeArticle.id).where(KnowledgeArticle.title == articles[1][0])
            )
            is None
        )
    embeddings = FlakyEmbeddings()
    bootstrap_demo.seed_articles_with_retry(engine, embeddings)
    assert embeddings.calls == 1


def test_bootstrap_marker_skips_later_reseeding(isolated_articles, monkeypatch):
    engine, articles = isolated_articles
    version = f"test-{uuid4()}"
    monkeypatch.setattr(bootstrap_demo, "SEED_VERSION", version)
    monkeypatch.setattr(
        bootstrap_demo, "get_settings", lambda: SimpleNamespace(nvidia_api_key=SecretStr("test"))
    )
    monkeypatch.setattr(bootstrap_demo, "seed_demo_data", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(bootstrap_demo, "EmbeddingService", FlakyEmbeddings)
    try:
        bootstrap_demo.bootstrap_demo(engine)
        with Session(engine) as session, session.begin():
            session.execute(
                delete(KnowledgeArticle).where(KnowledgeArticle.title == articles[0][0])
            )
        bootstrap_demo.bootstrap_demo(engine)
        with Session(engine) as session:
            assert (
                session.scalar(
                    select(KnowledgeArticle.id).where(KnowledgeArticle.title == articles[0][0])
                )
                is None
            )
            assert (
                session.scalar(
                    text("SELECT 1 FROM demo_seed_state WHERE version = :v"), {"v": version}
                )
                == 1
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM demo_seed_state WHERE version = :v"), {"v": version}
            )
