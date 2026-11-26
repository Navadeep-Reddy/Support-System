from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from support_agent.schemas.account import ResetResult


class ConversationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="New conversation", max_length=200)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Title must not be blank")
        return value.strip()


class ConversationData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationList(BaseModel):
    items: list[ConversationData]


class Citation(BaseModel):
    article_id: UUID
    chunk_id: UUID
    article_title: str
    section: str


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rating: Literal["positive", "negative"]
    comment: str | None = None


class FeedbackData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rating: Literal["positive", "negative"]
    comment: str | None
    updated_at: datetime


class ApprovalCard(BaseModel):
    action_id: UUID
    action_type: Literal["request_password_reset"]
    status: Literal["pending", "approved", "rejected", "executed", "failed"]
    account_display_name: str
    created_at: datetime
    decided_at: datetime | None
    result: ResetResult | None


class RunData(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Literal["running", "waiting_for_approval", "completed", "failed"]
    conversation_id: UUID


class MessageData(BaseModel):
    id: UUID
    conversation_id: UUID
    run_id: UUID | None
    role: Literal["user", "assistant", "action"]
    content: str | None
    created_at: datetime
    citations: list[Citation]
    approval: ApprovalCard | None
    feedback: FeedbackData | None


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value.strip()


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool = Field(strict=True)


class TurnError(BaseModel):
    code: str
    message: str
    retryable: bool = False


class TurnResponse(BaseModel):
    run_id: UUID
    conversation_id: UUID
    status: Literal["completed", "waiting_for_approval", "failed"]
    messages: list[MessageData]
    pending_approval: ApprovalCard | None
    error: TurnError | None


class HistoryResponse(BaseModel):
    conversation: ConversationData
    messages: list[MessageData]
    active_run: RunData | None
    pending_approval: ApprovalCard | None
