from typing import Any, Literal
from uuid import UUID

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from support_agent.schemas.account import PaymentData, SubscriptionData
from support_agent.schemas.knowledge import RetrievedChunk
from support_agent.services.accounts import AccountError, AccountService
from support_agent.services.knowledge import KnowledgeError, KnowledgeService


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ToolResult[T](BaseModel):
    success: bool
    data: T | None = None
    error: ToolError | None = None


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=512)

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        value = value.strip()
        if not value or len(value.encode("utf-8")) > 512:
            raise ValueError("Query must be nonblank and at most 512 UTF-8 bytes")
        return value


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchResults(BaseModel):
    chunks: list[RetrievedChunk]


class ApprovalRequired(BaseModel):
    status: Literal["approval_required"] = "approval_required"


def _schema_placeholder(**kwargs: Any) -> None:
    raise RuntimeError("Tool schemas cannot be executed directly")


def tool_definitions() -> list[StructuredTool]:
    """These objects supply model-visible schemas, not executable capabilities."""
    descriptions = [
        (
            "search_knowledge_base",
            SearchInput,
            "Search public support policies and troubleshooting guidance using a focused query.",
        ),
        (
            "get_current_subscription",
            EmptyInput,
            "Fetch the current customer's live subscription, plan and billing period.",
        ),
        (
            "get_payment_status",
            EmptyInput,
            "Fetch the current customer's latest payment and failure reason, if any.",
        ),
        (
            "request_password_reset",
            EmptyInput,
            "Request a simulated password reset; explicit customer approval is always required.",
        ),
    ]
    return [
        StructuredTool.from_function(
            func=_schema_placeholder, name=name, description=description, args_schema=schema
        )
        for name, schema, description in descriptions
    ]


class SupportTools:
    def __init__(
        self, customer_id: UUID, accounts: AccountService, knowledge: KnowledgeService | None
    ):
        self.customer_id = customer_id
        self.accounts = accounts
        self.knowledge = knowledge

    def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult[Any]:
        try:
            if name == "search_knowledge_base":
                args = SearchInput.model_validate(arguments)
                if self.knowledge is None:
                    raise KnowledgeError("PROVIDER_UNAVAILABLE", "Knowledge search is unavailable.")
                data = SearchResults(
                    chunks=[
                        RetrievedChunk.model_validate(item)
                        for item in self.knowledge.search(args.query)
                    ]
                )
            elif name == "get_current_subscription":
                EmptyInput.model_validate(arguments)
                data = SubscriptionData.model_validate(
                    self.accounts.current_subscription(self.customer_id)
                )
            elif name == "get_payment_status":
                EmptyInput.model_validate(arguments)
                data = PaymentData.model_validate(self.accounts.latest_payment(self.customer_id))
            elif name == "request_password_reset":
                EmptyInput.model_validate(arguments)
                # The graph must pause here; this adapter cannot execute a reset.
                data = ApprovalRequired()
            else:
                return ToolResult(
                    success=False,
                    error=ToolError(
                        code="UNKNOWN_TOOL", message="The requested tool is not available."
                    ),
                )
        except ValidationError:
            return ToolResult(
                success=False,
                error=ToolError(code="INVALID_TOOL_INPUT", message="The tool input is invalid."),
            )
        except (AccountError, KnowledgeError) as exc:
            return ToolResult(
                success=False,
                error=ToolError(
                    code=exc.code, message=str(exc), retryable=exc.code == "PROVIDER_UNAVAILABLE"
                ),
            )
        return ToolResult(success=True, data=data)
