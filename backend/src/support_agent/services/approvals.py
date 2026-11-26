"""Serialize decisions and execute the previously prepared action transactionally."""

import time
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from support_agent.models import ActionApproval, AgentRun, Conversation
from support_agent.models.base import utc_now
from support_agent.repositories.accounts import AccountRepository
from support_agent.repositories.conversations import ConversationRepository
from support_agent.services.accounts import AccountService
from support_agent.services.conversations import ConversationError


class ApprovalService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owned_run(self, customer_id: UUID, action_id: UUID) -> tuple[UUID, UUID]:
        row = self.session.execute(
            select(AgentRun.id, AgentRun.conversation_id)
            .join(ActionApproval, ActionApproval.run_id == AgentRun.id)
            .join(Conversation, AgentRun.conversation_id == Conversation.id)
            .where(ActionApproval.id == action_id, Conversation.customer_id == customer_id)
        ).one_or_none()
        if row is None:
            raise ConversationError("NOT_FOUND", "The action was not found.")
        return row.id, row.conversation_id

    def decide(
        self, customer_id: UUID, run_id: UUID, action_id: UUID, approved: bool, deadline: float
    ) -> None:
        budget = deadline - time.monotonic()
        if budget <= 0:
            raise TimeoutError("Decision exceeded the active deadline")
        self.session.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{max(1, int(budget * 1000))}ms"},
        )
        run = ConversationRepository(self.session).owned_run_for_update(customer_id, run_id)
        action = AccountRepository(self.session).owned_approval_for_update(customer_id, action_id)
        if run is None or action is None or action.run_id != run_id:
            raise ConversationError("NOT_FOUND", "The action was not found.")
        if action.status != "pending":
            raise ConversationError("APPROVAL_RESOLVED", "The action has already been decided.")
        if run.status != "waiting_for_approval":
            raise ConversationError("RUN_ACTIVE", "The run is not waiting for a decision.")
        action.decided_at = utc_now()
        action.status = "approved" if approved else "rejected"
        self.session.flush()
        if approved:
            AccountService(self.session).execute_reset(customer_id, action_id)
        # Commit the decision and transition together so startup recovery can release
        # an interrupted continuation without replaying the already decided action.
        run.status = "running"
        self.session.flush()
        if time.monotonic() >= deadline:
            raise TimeoutError("Decision exceeded the active deadline")
