import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from support_agent.agent.context import ContextError
from support_agent.services.accounts import AccountError
from support_agent.services.conversations import ConversationError
from support_agent.services.knowledge import KnowledgeError

logger = logging.getLogger(__name__)


_ERROR_BY_STATUS: Mapping[int, tuple[str, str]] = {
    401: ("SESSION_REQUIRED", "A valid session is required."),
    404: ("NOT_FOUND", "The requested resource was not found."),
    409: ("CONFLICT", "The request conflicts with the current resource state."),
    422: ("VALIDATION_ERROR", "Request validation failed."),
}


def _error_response(
    status_code: int, code: str, message: str, *, retryable: bool = False, details: Any = None
) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    body: dict[str, Any] = {"error": error}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ContextError)
    async def handle_context_error(_request: Request, exc: ContextError) -> JSONResponse:
        return _error_response(422, "VALIDATION_ERROR", str(exc))

    @app.exception_handler(AccountError)
    async def handle_account_error(_request: Request, exc: AccountError) -> JSONResponse:
        status = {"NOT_FOUND": 404, "INVALID_ACTION": 409, "APPROVAL_REQUIRED": 409}.get(
            exc.code, 500
        )
        return _error_response(
            status, exc.code, str(exc) if status < 500 else "An unexpected error occurred."
        )

    @app.exception_handler(ConversationError)
    async def handle_conversation_error(_request: Request, exc: ConversationError) -> JSONResponse:
        status = {
            "NOT_FOUND": 404,
            "VALIDATION_ERROR": 422,
            "RUN_ACTIVE": 409,
            "RUN_RESOLVED": 409,
            "APPROVAL_REQUIRED": 409,
            "APPROVAL_RESOLVED": 409,
            "DECISION_PENDING": 503,
        }.get(exc.code, 500)
        return _error_response(status, exc.code, str(exc), retryable=False)

    @app.exception_handler(KnowledgeError)
    async def handle_knowledge_error(_request: Request, exc: KnowledgeError) -> JSONResponse:
        status = {
            "NOT_FOUND": 404,
            "VALIDATION_ERROR": 422,
            "SECTION_TOO_LARGE": 422,
            "PROVIDER_UNAVAILABLE": 503,
        }.get(exc.code, 500)
        return _error_response(status, exc.code, str(exc), retryable=status == 503)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        safe_details = [
            {"location": item.get("loc"), "message": item.get("msg"), "type": item.get("type")}
            for item in exc.errors()
        ]
        return _error_response(
            422, "VALIDATION_ERROR", "Request validation failed.", details=safe_details
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, default_message = _ERROR_BY_STATUS.get(
            exc.status_code, ("HTTP_ERROR", "The request could not be completed.")
        )
        # Only expose a handler-provided string for client errors; never leak server details.
        message = (
            exc.detail if exc.status_code < 500 and isinstance(exc.detail, str) else default_message
        )
        return _error_response(exc.status_code, code, message)

    @app.exception_handler(OperationalError)
    async def handle_database_unavailable(_request: Request, exc: OperationalError) -> JSONResponse:
        logger.exception("database_connection_failed", exc_info=exc)
        return _error_response(
            503,
            "DATABASE_UNAVAILABLE",
            "The database is temporarily unavailable.",
            retryable=True,
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_database_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database_operation_failed", exc_info=exc)
        return _error_response(500, "INTERNAL_ERROR", "An internal error occurred.")

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_application_error", exc_info=exc)
        return _error_response(500, "INTERNAL_ERROR", "An internal error occurred.")
