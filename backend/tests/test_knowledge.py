from collections.abc import Iterator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from scripts.seed_data import seed_demo_data
from scripts.seed_knowledge import ARTICLES, seed_knowledge
from support_agent.api.knowledge import get_embeddings
from support_agent.core.config import get_settings
from support_agent.core.database import get_db_session
from support_agent.core.schema import initialize_schema
from support_agent.main import app
from support_agent.models import Customer, KnowledgeArticle, KnowledgeChunk
from support_agent.services.embeddings import EmbeddingService
from support_agent.services.knowledge import split_sections


class FakeEmbeddings:
    fail = False

    def embed_passages(self, texts):
        if self.fail:
            raise RuntimeError("provider failure")
        return [[1.0] + [0.0] * 2047 for _ in texts]

    def embed_query(self, _query):
        return [1.0] + [0.0] * 2047


@pytest.fixture
def environment() -> Iterator[tuple[TestClient, Session, FakeEmbeddings]]:
    engine = create_engine(get_settings().test_database_url)
    initialize_schema(engine)
    seed_demo_data(engine)
    with engine.connect() as connection:
        transaction = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        embeddings = FakeEmbeddings()

        def db():
            try:
                yield session
            except Exception:
                session.rollback()
                raise

        app.dependency_overrides[get_db_session] = db
        app.dependency_overrides[get_embeddings] = lambda: embeddings
        client = TestClient(app)
        yield client, session, embeddings
        client.close()
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
    engine.dispose()


def test_seed_is_repeatable(environment) -> None:
    _, session, embeddings = environment
    seed_knowledge(session, embeddings)
    seed_knowledge(session, embeddings)
    for title, _, _ in ARTICLES:
        assert (
            session.scalar(
                select(func.count())
                .select_from(KnowledgeArticle)
                .where(KnowledgeArticle.title == title)
            )
            == 1
        )


def test_chunking_hierarchy_preamble_and_code_fences() -> None:
    sections = split_sections(
        "Intro\n# Parent\n## Child\nText\n```md\n# Not a heading\n```\n## Empty\n# Last\nEnd"
    )
    assert [s.path for s in sections] == ["Introduction", "Parent > Child", "Last"]
    assert "# Not a heading" in sections[1].text
    assert split_sections("Plain article")[0].text == "Plain article"


def test_crud_auth_indexing_failure_and_search(environment) -> None:
    from support_agent.services.knowledge import KnowledgeService

    client, session, embeddings = environment
    assert client.get("/knowledge/articles").status_code == 401
    customer = session.scalar(select(Customer).where(Customer.handle == "alex"))
    assert client.post("/sessions", json={"customer_id": str(customer.id)}).status_code == 200
    payload = {
        "title": f"Test {uuid4()}",
        "category": "billing",
        "body": "## Refund\nInitial payments only.",
    }
    created = client.post("/knowledge/articles", json=payload)
    assert created.status_code == 201, created.text
    article_id = created.json()["id"]
    assert client.get(f"/knowledge/articles/{article_id}").json()["body"] == payload["body"]
    assert any(
        item["id"] == article_id for item in client.get("/knowledge/articles").json()["items"]
    )
    results = KnowledgeService(session, embeddings).search("refund")
    assert any(str(result.article_id) == article_id for result in results)
    embeddings.embed_query = lambda _query: [0.0, 1.0] + [0.0] * 2046
    assert KnowledgeService(session, embeddings).search("unrelated") == []
    embeddings.fail = True
    failed = client.put(
        f"/knowledge/articles/{article_id}", json={**payload, "body": "## New\nChanged"}
    )
    assert failed.status_code == 503
    assert client.get(f"/knowledge/articles/{article_id}").json()["body"] == payload["body"]
    original = session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))
    assert original.source_text == "Initial payments only."
    embeddings.fail = False
    updated = client.put(
        f"/knowledge/articles/{article_id}", json={**payload, "body": "## New\nChanged"}
    )
    assert updated.status_code == 200
    embeddings.embed_query = lambda _query: [1.0, 0.0] + [0.0] * 2046
    updated_results = KnowledgeService(session, embeddings).search("changed")
    assert any(
        str(item.article_id) == article_id and item.text == "Changed" for item in updated_results
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.article_id == article_id)
        )
        == 1
    )
    assert client.delete(f"/knowledge/articles/{article_id}").status_code == 204
    assert client.get(f"/knowledge/articles/{article_id}").status_code == 404
    assert all(
        str(item.article_id) != article_id
        for item in KnowledgeService(session, embeddings).search("changed")
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.article_id == article_id)
        )
        == 0
    )


def test_database_failure_rolls_back_article_and_chunks(environment) -> None:
    client, session, _ = environment
    customer = session.scalar(select(Customer).where(Customer.handle == "alex"))
    client.post("/sessions", json={"customer_id": str(customer.id)})
    payload = {"title": f"Test {uuid4()}", "category": "billing", "body": "## Old\nOriginal"}
    response = client.post("/knowledge/articles", json=payload)
    article_id = response.json()["id"]
    connection = session.connection()

    def fail_insert(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("INSERT INTO knowledge_chunks"):
            raise SQLAlchemyError("injected database failure")

    event.listen(connection, "before_cursor_execute", fail_insert)
    try:
        response = client.put(
            f"/knowledge/articles/{article_id}", json={**payload, "body": "## New\nChanged"}
        )
        assert response.status_code == 500
    finally:
        event.remove(connection, "before_cursor_execute", fail_insert)
    assert client.get(f"/knowledge/articles/{article_id}").json()["body"] == payload["body"]
    chunk = session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))
    assert chunk.source_text == "Original"


def test_database_failure_rolls_back_delete(environment) -> None:
    client, session, _ = environment
    customer = session.scalar(select(Customer).where(Customer.handle == "alex"))
    client.post("/sessions", json={"customer_id": str(customer.id)})
    payload = {"title": f"Test {uuid4()}", "category": "billing", "body": "## Old\nOriginal"}
    article_id = client.post("/knowledge/articles", json=payload).json()["id"]
    connection = session.connection()

    def fail_after_delete(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.startswith("DELETE FROM knowledge_articles"):
            raise SQLAlchemyError("injected database failure")

    event.listen(connection, "after_cursor_execute", fail_after_delete)
    try:
        assert client.delete(f"/knowledge/articles/{article_id}").status_code == 500
    finally:
        event.remove(connection, "after_cursor_execute", fail_after_delete)
    assert client.get(f"/knowledge/articles/{article_id}").status_code == 200
    chunk = session.scalar(select(KnowledgeChunk).where(KnowledgeChunk.article_id == article_id))
    assert chunk.source_text == "Original"


def test_missing_article_checked_before_provider_initialization(environment, monkeypatch) -> None:
    client, session, _ = environment
    customer = session.scalar(select(Customer).where(Customer.handle == "alex"))
    client.post("/sessions", json={"customer_id": str(customer.id)})

    def unavailable(**_kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr("support_agent.services.embeddings.NVIDIAEmbeddings", unavailable)
    app.dependency_overrides[get_embeddings] = lambda: EmbeddingService()
    payload = {"title": "Title", "category": "billing", "body": "Text"}
    assert client.put(f"/knowledge/articles/{uuid4()}", json=payload).status_code == 404
    assert client.post("/knowledge/articles", json=payload).status_code == 503


def test_large_and_invalid_article_rejected(environment) -> None:
    client, session, _ = environment
    customer = session.scalar(select(Customer).where(Customer.handle == "alex"))
    client.post("/sessions", json={"customer_id": str(customer.id)})
    response = client.post(
        "/knowledge/articles", json={"title": "Title", "category": "x", "body": "a" * 600}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "SECTION_TOO_LARGE"
    assert (
        client.post(
            "/knowledge/articles", json={"title": " ", "category": "x", "body": "x"}
        ).status_code
        == 422
    )
