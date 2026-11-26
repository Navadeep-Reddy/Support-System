from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from support_agent.api.sessions import Database, current_customer
from support_agent.schemas.conversation import (
    ApprovalDecision,
    ChatInput,
    ConversationData,
    ConversationInput,
    ConversationList,
    FeedbackData,
    FeedbackInput,
    HistoryResponse,
    TurnResponse,
)
from support_agent.schemas.customer import CustomerResponse
from support_agent.services.conversations import ConversationService
from support_agent.services.turns import TurnService

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


def get_turn_service(request: Request) -> TurnService:
    return TurnService(request.app.state.agent_turns)


Turns = Annotated[TurnService, Depends(get_turn_service)]


@router.post("/conversations/{conversation_id}/chat", response_model=TurnResponse)
async def chat(
    conversation_id: UUID, data: ChatInput, customer: Customer, turns: Turns
) -> TurnResponse:
    return await turns.chat(customer.id, conversation_id, data.message)


@router.post("/approvals/{action_id}", response_model=TurnResponse)
async def decide_approval(
    action_id: UUID, data: ApprovalDecision, customer: Customer, turns: Turns
) -> TurnResponse:
    return await turns.decide(customer.id, action_id, data.approved)


@router.put("/messages/{message_id}/feedback", response_model=FeedbackData)
def feedback(
    message_id: UUID, data: FeedbackInput, db: Database, customer: Customer
) -> FeedbackData:
    result = ConversationService(db).feedback(customer.id, message_id, data)
    db.commit()
    return result
