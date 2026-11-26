import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from support_agent.api.errors import register_exception_handlers
from support_agent.api.sessions import router as session_router
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
    description="Backend API for Aatra subscription support.",
    version="0.1.0",
    lifespan=lifespan,
)
settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret.get_secret_value(),
    session_cookie=settings.session_cookie_name,
    https_only=settings.session_cookie_secure,
    same_site="lax",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_exception_handlers(app)
app.include_router(session_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
