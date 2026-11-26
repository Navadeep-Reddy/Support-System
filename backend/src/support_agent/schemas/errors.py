from typing import Any

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str
    retryable: bool


class ErrorEnvelope(BaseModel):
    error: ApiError
    details: list[dict[str, Any]] | None = None
