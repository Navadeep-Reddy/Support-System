import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from support_agent.api.errors import register_exception_handlers
from support_agent.core.config import get_settings
from support_agent.core.database import get_engine
from support_agent.core.logging_config import configure_logging
from support_agent.core.tracing import configure_langsmith_tracing

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    # LangChain/LangGraph automatically trace supported runs from these variables.
    configure_langsmith_tracing(settings)
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
    logger.info("application_started", extra={"database": "connected"})
    yield
    get_engine().dispose()
    logger.info("application_stopped")


app = FastAPI(
    title="Aatra Support Agent API",
    description="Backend API for the fictional Aatra subscription support demo.",
    version="0.1.0",
    lifespan=lifespan,
)
register_exception_handlers(app)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
