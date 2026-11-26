from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from support_agent.models import ActionApproval, AgentRun, Conversation, Feedback, Message
from support_agent.models.base import utc_now


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owned(self, customer_id: UUID, conversation_id: UUID) -> Conversation | None:
        return self.session.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.customer_id == customer_id
            )
        )

    def list_owned(self, customer_id: UUID) -> list[Conversation]:
        return list(
            self.session.scalars(
                select(Conversation)
                .where(Conversation.customer_id == customer_id)
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            )
        )

    def messages(self, conversation_id: UUID) -> list[Message]:
        return list(
            self.session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.id)
            )
        )

    def active_run(self, conversation_id: UUID) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun).where(
                AgentRun.conversation_id == conversation_id,
                AgentRun.status.in_(("running", "waiting_for_approval")),
            )
        )

    def owned_run_for_update(self, customer_id: UUID, run_id: UUID) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun)
            .join(Conversation)
            .where(AgentRun.id == run_id, Conversation.customer_id == customer_id)
            .with_for_update(of=AgentRun)
        )

    def pending_approval(self, run_id: UUID) -> ActionApproval | None:
        return self.session.scalar(
            select(ActionApproval).where(
                ActionApproval.run_id == run_id, ActionApproval.status == "pending"
            )
        )

    def owned_message(self, customer_id: UUID, message_id: UUID) -> Message | None:
        return self.session.scalar(
            select(Message)
            .join(Conversation)
            .where(Message.id == message_id, Conversation.customer_id == customer_id)
        )

    def feedback(self, customer_id: UUID, message_id: UUID) -> Feedback | None:
        return self.session.scalar(
            select(Feedback).where(
                Feedback.customer_id == customer_id, Feedback.message_id == message_id
            )
        )

    def upsert_feedback(
        self, customer_id: UUID, message_id: UUID, rating: str, comment: str | None
    ) -> Feedback:
        statement = insert(Feedback).values(
            customer_id=customer_id, message_id=message_id, rating=rating, comment=comment
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Feedback.customer_id, Feedback.message_id],
            set_={"rating": rating, "comment": comment, "updated_at": utc_now()},
        ).returning(Feedback)
        return self.session.scalars(statement, execution_options={"populate_existing": True}).one()


def recover_running_runs(session: Session) -> int:
    now = utc_now()
    result = session.execute(
        update(AgentRun)
        .where(AgentRun.status == "running")
        .values(status="failed", finished_at=now, updated_at=now)
    )
    return result.rowcount
