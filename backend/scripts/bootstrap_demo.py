"""Initialize fictional demo data, resuming article indexing after interruptions."""

import argparse
import time
from collections.abc import Callable

from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session

from scripts.seed_data import seed_demo_data
from scripts.seed_knowledge import ARTICLES
from support_agent.core.config import get_settings
from support_agent.core.database import get_engine
from support_agent.core.schema import initialize_schema
from support_agent.models import KnowledgeArticle
from support_agent.schemas.knowledge import ArticleInput
from support_agent.services.embeddings import EmbeddingService
from support_agent.services.knowledge import KnowledgeError, KnowledgeService

SEED_VERSION = "demo-v2"


def seed_articles_with_retry(
    engine: Engine,
    embeddings: EmbeddingService,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Commit each article independently; retry provider failures until interrupted."""
    for title, category, body in ARTICLES:
        delay = 1.0
        while True:
            try:
                with Session(engine) as session:
                    if session.scalar(
                        select(KnowledgeArticle.id).where(KnowledgeArticle.title == title)
                    ):
                        break
                    KnowledgeService(session, embeddings).save(
                        ArticleInput(title=title, category=category, body=body)
                    )
                    session.commit()
                print(f"Indexed: {title}", flush=True)
                break
            except KnowledgeError as exc:
                if exc.code != "PROVIDER_UNAVAILABLE":
                    raise
                print(
                    f"Indexing {title!r} failed; retrying in {delay:g}s (Ctrl+C to stop).",
                    flush=True,
                )
                sleep(delay)
                delay = min(delay * 2, 30.0)


def bootstrap_demo(engine: Engine, *, force: bool = False) -> None:
    initialize_schema(engine)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE IF NOT EXISTS demo_seed_state (version text PRIMARY KEY)")
        )
        complete = connection.scalar(
            text("SELECT 1 FROM demo_seed_state WHERE version = :version"),
            {"version": SEED_VERSION},
        )
    if complete and not force:
        print("Demo seed already complete; preserving existing data.")
        return
    if not get_settings().nvidia_api_key.get_secret_value().strip():
        raise RuntimeError("NVIDIA_API_KEY is required to index the demo knowledge articles.")
    if force:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM demo_seed_state WHERE version = :version"),
                {"version": SEED_VERSION},
            )
    seed_demo_data(engine, refresh_existing=force)
    seed_articles_with_retry(engine, EmbeddingService())
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO demo_seed_state (version) VALUES (:version) ON CONFLICT DO NOTHING"),
            {"version": SEED_VERSION},
        )
    print("Demo seed complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh", action="store_true", help="Refresh demo account data and add missing articles"
    )
    args = parser.parse_args()
    try:
        bootstrap_demo(get_engine(), force=args.refresh)
    except KeyboardInterrupt:
        print("\nSeeding interrupted. Re-run ./start.sh to resume missing articles.")
        raise SystemExit(130) from None


if __name__ == "__main__":
    main()
