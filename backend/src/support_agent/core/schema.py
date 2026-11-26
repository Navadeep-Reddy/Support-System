from sqlalchemy import Engine, text

from support_agent.models import Base


def initialize_schema(engine: Engine) -> None:
    """Enable required PostgreSQL extensions and create missing application tables."""
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)
