import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

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

logger = logging.getLogger(__name__)
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


@router.post("/conversations/{conversation_id}/chat/stream")
async def stream_chat(
    conversation_id: UUID, data: ChatInput, customer: Customer, turns: Turns
) -> StreamingResponse:
    # Reserve before returning headers so ownership/conflict/validation errors remain HTTP errors.
    state = turns.runner.prepare_start(customer.id, conversation_id, data.message)
    queue: asyncio.Queue[dict] = asyncio.Queue()
    connected = True

    def emit(kind: str, content: str) -> None:
        if connected:
            queue.put_nowait({"type": kind, "text": content})

    async def run() -> None:
        try:
            result = await turns.runner.start_prepared(customer.id, conversation_id, state, emit)
            response = turns._response(customer.id, conversation_id, result)
            if connected:
                queue.put_nowait({"type": "done", "turn": response.model_dump(mode="json")})
        except Exception:
            logger.exception("stream_chat_failed conversation_id=%s", conversation_id)
            try:
                turns.runner._finish(customer.id, UUID(state["run_id"]), {"status": "failed"})
            except Exception:
                logger.exception("stream_chat_cleanup_failed conversation_id=%s", conversation_id)
            if connected:
                queue.put_nowait(
                    {"type": "error", "message": "The response was interrupted. Refresh history."}
                )

    # A disconnected browser must not cancel an already-reserved turn or strand a run.
    task = asyncio.create_task(run())
    turns.runner.background_tasks.add(task)
    task.add_done_callback(turns.runner.background_tasks.discard)

    async def events() -> AsyncIterator[str]:
        nonlocal connected
        try:
            yield json.dumps({"type": "started", "run_id": state["run_id"]}) + "\n"
            while True:
                event = await queue.get()
                yield json.dumps(event) + "\n"
                if event["type"] in ("done", "error"):
                    break
        finally:
            connected = False

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
