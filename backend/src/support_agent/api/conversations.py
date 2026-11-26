from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from support_agent.api.sessions import Database, current_customer
from support_agent.schemas.conversation import (
    ConversationData,
    ConversationInput,
    ConversationList,
    FeedbackData,
    FeedbackInput,
    HistoryResponse,
)
from support_agent.schemas.customer import CustomerResponse
from support_agent.services.conversations import ConversationService

router = APIRouter(tags=["conversations"])
Customer = Annotated[CustomerResponse, Depends(current_customer)]


@router.get("/conversations", response_model=ConversationList)
def list_conversations(db: Database, customer: Customer) -> ConversationList:
    return ConversationList(items=ConversationService(db).list_conversations(customer.id))


@router.post("/conversations", response_model=ConversationData, status_code=201)
def create_conversation(
    data: ConversationInput, db: Database, customer: Customer
) -> ConversationData:
    conversation = ConversationService(db).create(customer.id, data.title)
    db.commit()
    return conversation


@router.get("/conversations/{conversation_id}/messages", response_model=HistoryResponse)
def history(conversation_id: UUID, db: Database, customer: Customer) -> HistoryResponse:
    return ConversationService(db).history(customer.id, conversation_id)


@router.put("/messages/{message_id}/feedback", response_model=FeedbackData)
def feedback(
    message_id: UUID, data: FeedbackInput, db: Database, customer: Customer
) -> FeedbackData:
    result = ConversationService(db).feedback(customer.id, message_id, data)
    db.commit()
    return result
