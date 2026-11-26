from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from support_agent.core.config import get_settings


@lru_cache

def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache

def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db_session() -> Iterator[Session]:
    """FastAPI dependency that provides one request-scoped SQLAlchemy session."""
    with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
