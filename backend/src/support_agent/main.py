import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from support_agent.api.conversations import router as conversation_router
from support_agent.api.errors import register_exception_handlers
from support_agent.api.knowledge import router as knowledge_router
from support_agent.api.sessions import router as session_router
from support_agent.core.config import get_settings
from support_agent.core.database import get_engine
from support_agent.core.logging_config import configure_logging
from support_agent.core.tracing import configure_langsmith_tracing
from support_agent.repositories.conversations import recover_running_runs
from support_agent.schemas.errors import ErrorEnvelope
from support_agent.services.agent_turns import open_agent_turns

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    # LangChain/LangGraph automatically trace supported runs from these variables.
    configure_langsmith_tracing(settings)
    with Session(get_engine()) as session:
        recovered = recover_running_runs(session)
        session.commit()
    logger.info("startup_runs_recovered count=%d", recovered)
    async with open_agent_turns(get_engine()) as runner:
        app.state.agent_turns = runner
        logger.info("application_started", extra={"database": "connected"})
        yield
    get_engine().dispose()
    logger.info("application_stopped")


app = FastAPI(
    title="Aatra Support Agent API",
    description="Backend API for Aatra subscription support.",
    version="0.1.0",
    lifespan=lifespan,
    responses={
        401: {"model": ErrorEnvelope, "description": "Session required"},
        404: {"model": ErrorEnvelope, "description": "Resource not found"},
        409: {"model": ErrorEnvelope, "description": "Request conflict"},
        422: {"model": ErrorEnvelope, "description": "Invalid request"},
        503: {"model": ErrorEnvelope, "description": "Service unavailable"},
        500: {"model": ErrorEnvelope, "description": "Internal error"},
    },
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
app.include_router(knowledge_router)
app.include_router(conversation_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
