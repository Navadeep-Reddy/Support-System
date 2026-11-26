"""Application-level coordination of HTTP turns and approval decisions."""

import asyncio
import logging
import time
from uuid import UUID

from support_agent.schemas.conversation import TurnError, TurnResponse
from support_agent.services.agent_turns import AgentTurns
from support_agent.services.approvals import ApprovalService
from support_agent.services.conversations import ConversationError, ConversationService

logger = logging.getLogger(__name__)


class TurnService:
    def __init__(self, runner: AgentTurns) -> None:
        self.runner = runner

    def _response(self, customer_id: UUID, conversation_id: UUID, result: dict) -> TurnResponse:
        with self.runner.sessions() as session:
            history = ConversationService(session).history(customer_id, conversation_id)
        code = result.get("error")
        error = (
            TurnError(
                code=code,
                message="The assistant couldn't finish this turn. "
                "Check the action card for its outcome.",
                retryable=code == "PROVIDER_UNAVAILABLE",
            )
            if code
            else None
        )
        return TurnResponse(
            run_id=result["run_id"],
            conversation_id=conversation_id,
            status=result["status"],
            messages=[
                message for message in history.messages if message.run_id == result["run_id"]
            ],
            pending_approval=history.pending_approval
            if (
                result["status"] == "waiting_for_approval"
                and history.active_run is not None
                and history.active_run.id == result["run_id"]
                and history.active_run.status == "waiting_for_approval"
            )
            else None,
            error=error,
        )

    async def chat(self, customer_id: UUID, conversation_id: UUID, message: str) -> TurnResponse:
        started = time.monotonic()
        result = await self.runner.start(customer_id, conversation_id, message)
        logger.info(
            "chat_finished conversation_id=%s run_id=%s status=%s elapsed_ms=%d",
            conversation_id,
            result["run_id"],
            result["status"],
            (time.monotonic() - started) * 1000,
        )
        return self._response(customer_id, conversation_id, result)

    def _decide(
        self, customer_id: UUID, run_id: UUID, action_id: UUID, approved: bool, deadline: float
    ) -> None:
        try:
            with self.runner.sessions.begin() as session:
                ApprovalService(session).decide(customer_id, run_id, action_id, approved, deadline)
        except Exception as exc:
            if getattr(getattr(exc, "orig", None), "sqlstate", None) == "57014":
                raise TimeoutError("Decision exceeded the active deadline") from exc
            raise

    async def _settle_abandoned_decision(
        self, task: asyncio.Task, customer_id: UUID, run_id: UUID, action_id: UUID
    ) -> None:
        """Resolve the run after a timed-out worker finishes, without blocking HTTP."""
        try:
            await task
        except ConversationError:
            # Another serialized decision may own the run; never finalize it here.
            return
        except Exception:
            logger.warning("abandoned_approval_decision_failed run_id=%s", run_id, exc_info=True)
            await asyncio.to_thread(
                self.runner.fail_pending_decision, customer_id, run_id, action_id
            )
        else:
            await asyncio.to_thread(self.runner._finish, customer_id, run_id, {"status": "failed"})

    def _owned_run(self, customer_id: UUID, action_id: UUID) -> tuple[UUID, UUID]:
        with self.runner.sessions() as session:
            return ApprovalService(session).owned_run(customer_id, action_id)

    async def decide(self, customer_id: UUID, action_id: UUID, approved: bool) -> TurnResponse:
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.runner.settings.active_turn_deadline_seconds):
                run_id, conversation_id = await asyncio.to_thread(
                    self._owned_run, customer_id, action_id
                )
        except TimeoutError as exc:
            raise ConversationError(
                "DECISION_PENDING", "The decision outcome is being resolved. Refresh history."
            ) from exc
        try:
            deadline = await self.runner.decision_deadline(customer_id, run_id, action_id, started)
            if deadline <= time.monotonic():
                raise TimeoutError("Decision exceeded the active deadline")
            task = asyncio.create_task(
                asyncio.to_thread(self._decide, customer_id, run_id, action_id, approved, deadline)
            )
            try:
                async with asyncio.timeout(max(0.0, deadline - time.monotonic())):
                    await asyncio.shield(task)
            except (TimeoutError, asyncio.CancelledError) as exc:
                # The worker cannot be safely cancelled: it may have committed. Let it
                # finish and reconcile asynchronously; never claim an unknown outcome.
                cleanup = asyncio.create_task(
                    self._settle_abandoned_decision(task, customer_id, run_id, action_id)
                )
                self.runner.background_tasks.add(cleanup)
                cleanup.add_done_callback(self.runner.background_tasks.discard)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise ConversationError(
                    "DECISION_PENDING", "The decision outcome is being resolved. Refresh history."
                ) from exc
        except TimeoutError:
            cleanup = asyncio.create_task(
                asyncio.to_thread(self.runner.fail_pending_decision, customer_id, run_id, action_id)
            )
            self.runner.background_tasks.add(cleanup)
            cleanup.add_done_callback(self.runner.background_tasks.discard)
            try:
                async with asyncio.timeout(0.25):
                    failed = await asyncio.shield(cleanup)
            except TimeoutError as exc:
                raise ConversationError(
                    "DECISION_PENDING", "The decision outcome is being resolved. Refresh history."
                ) from exc
            if not failed:
                raise ConversationError("APPROVAL_RESOLVED", "The action has already been decided.")
            result = {"run_id": run_id, "status": "failed", "error": "DEADLINE_EXCEEDED"}
        else:
            result = await self.runner.resume(customer_id, run_id, active_started_at=started)
        logger.info(
            "approval_finished conversation_id=%s run_id=%s action_id=%s "
            "approved=%s status=%s elapsed_ms=%d",
            conversation_id,
            run_id,
            action_id,
            approved,
            result["status"],
            (time.monotonic() - started) * 1000,
        )
        return self._response(customer_id, conversation_id, result)
