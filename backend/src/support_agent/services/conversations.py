from typing import Literal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from support_agent.models import ActionApproval, AgentRun, Conversation, Message
from support_agent.models.base import utc_now
from support_agent.repositories.conversations import ConversationRepository
from support_agent.schemas.account import ResetPayload, ResetResult
from support_agent.schemas.conversation import (
    ApprovalCard,
    Citation,
    ConversationData,
    FeedbackData,
    FeedbackInput,
    HistoryResponse,
    MessageData,
    RunData,
)


class ConversationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def approval_card(approval: ActionApproval) -> ApprovalCard:
    payload = ResetPayload.model_validate(approval.validated_payload)
    if payload.action_id != approval.id or payload.action_type != approval.action_type:
        raise ConversationError("INVALID_ACTION", "The stored action is invalid.")
    result = (
        ResetResult.model_validate(approval.execution_result) if approval.execution_result else None
    )
    return ApprovalCard(
        action_id=approval.id,
        action_type=payload.action_type,
        status=approval.status,
        account_display_name=payload.account_display_name,
        created_at=approval.created_at,
        decided_at=approval.decided_at,
        result=result,
    )


class ConversationService:
    """All mutations belong to the caller's transaction."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = ConversationRepository(session)

    def _owned(self, customer_id: UUID, conversation_id: UUID) -> Conversation:
        conversation = self.repository.owned(customer_id, conversation_id)
        if conversation is None:
            raise ConversationError("NOT_FOUND", "The conversation was not found.")
        return conversation

    def create(self, customer_id: UUID, title: str) -> ConversationData:
        conversation = Conversation(customer_id=customer_id, title=title)
        self.session.add(conversation)
        self.session.flush()
        return ConversationData.model_validate(conversation)

    def list_conversations(self, customer_id: UUID) -> list[ConversationData]:
        return [
            ConversationData.model_validate(item)
            for item in self.repository.list_owned(customer_id)
        ]

    def history(self, customer_id: UUID, conversation_id: UUID) -> HistoryResponse:
        conversation = self._owned(customer_id, conversation_id)
        run = self.repository.active_run(conversation_id)
        pending = self.repository.pending_approval(run.id) if run else None
        messages = []
        for message in self.repository.messages(conversation_id):
            approval = (
                self.session.get(ActionApproval, message.approval_id)
                if message.approval_id
                else None
            )
            feedback = (
                self.repository.feedback(customer_id, message.id)
                if message.role == "assistant"
                else None
            )
            messages.append(
                MessageData(
                    id=message.id,
                    conversation_id=message.conversation_id,
                    run_id=message.run_id,
                    role=message.role,
                    content=message.content,
                    created_at=message.created_at,
                    citations=[Citation.model_validate(item) for item in message.citations],
                    approval=approval_card(approval) if approval else None,
                    feedback=FeedbackData.model_validate(feedback) if feedback else None,
                )
            )
        return HistoryResponse(
            conversation=ConversationData.model_validate(conversation),
            messages=messages,
            active_run=RunData.model_validate(run) if run else None,
            pending_approval=approval_card(pending) if pending else None,
        )

    def reserve_run(self, customer_id: UUID, conversation_id: UUID) -> RunData:
        self._owned(customer_id, conversation_id)
        try:
            with self.session.begin_nested():
                run = AgentRun(conversation_id=conversation_id, status="running")
                self.session.add(run)
                self.session.flush()
        except IntegrityError as exc:
            if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == (
                "uq_agent_runs_one_active_per_conversation"
            ):
                raise ConversationError("RUN_ACTIVE", "Finish the current turn first.") from exc
            raise
        return RunData.model_validate(run)

    def add_pending_approval(self, action: ActionApproval) -> None:
        try:
            with self.session.begin_nested():
                self.session.add(action)
                self.session.flush()
        except IntegrityError as exc:
            if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == (
                "uq_action_approvals_one_pending_per_run"
            ):
                raise ConversationError("RUN_ACTIVE", "An approval is already pending.") from exc
            raise

    def set_run_status(
        self,
        customer_id: UUID,
        run_id: UUID,
        status: Literal["running", "waiting_for_approval", "completed", "failed"],
    ) -> RunData:
        run = self.session.get(AgentRun, run_id)
        if run is None:
            raise ConversationError("NOT_FOUND", "The run was not found.")
        self._owned(customer_id, run.conversation_id)
        if run.status not in ("running", "waiting_for_approval"):
            raise ConversationError("RUN_RESOLVED", "The run is already resolved.")
        run.status = status
        run.finished_at = utc_now() if status in ("completed", "failed") else None
        self.session.flush()
        return RunData.model_validate(run)

    def add_message(
        self,
        customer_id: UUID,
        run_id: UUID,
        role: Literal["user", "assistant", "action"],
        content: str | None,
        *,
        citations: list[Citation] | None = None,
        retrieved: list[Citation] | None = None,
        approval_id: UUID | None = None,
    ) -> UUID:
        run = self.session.get(AgentRun, run_id)
        if run is None:
            raise ConversationError("NOT_FOUND", "The run was not found.")
        conversation = self._owned(customer_id, run.conversation_id)
        if run.status not in ("running", "waiting_for_approval"):
            raise ConversationError("RUN_RESOLVED", "The run is already resolved.")
        if role == "action":
            approval = self.session.get(ActionApproval, approval_id) if approval_id else None
            if content is not None or approval is None or approval.run_id != run_id:
                raise ConversationError("VALIDATION_ERROR", "Invalid approval message.")
        elif content is None or approval_id is not None:
            raise ConversationError("VALIDATION_ERROR", "Invalid text message.")
        validated_sources = {item.chunk_id: item for item in retrieved or []}
        accepted = (
            [
                validated_sources[item.chunk_id]
                for item in citations or []
                if item.chunk_id in validated_sources
            ]
            if role == "assistant"
            else []
        )
        message = Message(
            conversation_id=conversation.id,
            run_id=run_id,
            role=role,
            content=content,
            approval_id=approval_id,
            citations=[item.model_dump(mode="json") for item in accepted],
        )
        self.session.add(message)
        conversation.updated_at = utc_now()
        self.session.flush()
        return message.id

    def feedback(self, customer_id: UUID, message_id: UUID, data: FeedbackInput) -> FeedbackData:
        message = self.repository.owned_message(customer_id, message_id)
        if message is None:
            raise ConversationError("NOT_FOUND", "The message was not found.")
        if message.role != "assistant":
            raise ConversationError("VALIDATION_ERROR", "Feedback requires an assistant message.")
        feedback = self.repository.upsert_feedback(
            customer_id, message_id, data.rating, data.comment
        )
        return FeedbackData.model_validate(feedback)
