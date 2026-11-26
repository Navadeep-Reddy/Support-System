from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from support_agent.core.config import get_settings
from support_agent.core.tracing import configure_langsmith_tracing


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # LangChain/LangGraph automatically trace supported runs from these variables.
    configure_langsmith_tracing(get_settings())
    yield


app = FastAPI(
    title="Aatra Support Agent API",
    description="Backend API for the fictional Aatra subscription support demo.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
