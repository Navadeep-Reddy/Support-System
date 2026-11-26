from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+psycopg://support:support@localhost:5432/support_agent"
    test_database_url: str = "postgresql+psycopg://support:support@localhost:5432/support_agent_test"
    nvidia_api_key: SecretStr = SecretStr("")
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "nvidia/nemotron-3-super-120b-a12b"
    embedding_model: str = "nvidia/nemotron-3.5-embed-1b"
    embedding_dimensions: int = Field(default=2048, gt=0)
    session_secret: SecretStr = SecretStr("insecure-local-development-secret-change-me")
    session_cookie_name: str = "support_demo_session"
    session_cookie_secure: bool = False
    frontend_origin: str = "http://localhost:5173"
    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr = SecretStr("")
    langsmith_project: str = "aatra-support-agent"
    history_token_budget: int = Field(default=8192, gt=0)
    retrieval_top_k: int = Field(default=3, gt=0)
    retrieval_min_similarity: float = Field(default=0.35, ge=-1, le=1)
    max_retrieval_calls: int = Field(default=3, gt=0)
    max_llm_calls: int = Field(default=8, gt=0)
    max_tool_calls: int = Field(default=6, gt=0)
    max_consecutive_tool_failures: int = Field(default=2, gt=0)
    max_provider_retries: int = Field(default=2, ge=0)
    llm_timeout_seconds: float = Field(default=60, gt=0)
    active_turn_deadline_seconds: float = Field(default=120, gt=0)

    @model_validator(mode="after")
    def require_langsmith_key_when_tracing(self) -> "Settings":
        if self.langsmith_tracing and not self.langsmith_api_key.get_secret_value():
            raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true")
        return self

    @property
    def checkpointer_database_uri(self) -> str:
        """Convert SQLAlchemy's psycopg URL to the plain PostgreSQL URI expected by LangGraph."""
        parts = urlsplit(self.database_url)
        if parts.scheme != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use the postgresql+psycopg scheme")
        return urlunsplit(("postgresql", parts.netloc, parts.path, parts.query, parts.fragment))


@lru_cache

def get_settings() -> Settings:
    return Settings()
