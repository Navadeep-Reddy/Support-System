from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from support_agent.models import ActionApproval, AgentRun, Conversation, Payment, Plan, Subscription


class AccountRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def subscription(self, customer_id: UUID) -> tuple[Subscription, Plan] | None:
        row = self.session.execute(
            select(Subscription, Plan)
            .join(Plan, Subscription.plan_id == Plan.id)
            .where(Subscription.customer_id == customer_id)
        ).one_or_none()
        return (row[0], row[1]) if row else None

    def latest_payment(self, customer_id: UUID) -> Payment | None:
        return self.session.scalar(
            select(Payment)
            .where(Payment.customer_id == customer_id)
            .order_by(Payment.occurred_at.desc(), Payment.id.desc())
            .limit(1)
        )

    def owned_approval_for_update(
        self, customer_id: UUID, action_id: UUID
    ) -> ActionApproval | None:
        return self.session.scalar(
            select(ActionApproval)
            .join(AgentRun, ActionApproval.run_id == AgentRun.id)
            .join(Conversation, AgentRun.conversation_id == Conversation.id)
            .where(ActionApproval.id == action_id, Conversation.customer_id == customer_id)
            .with_for_update(of=ActionApproval)
        )
