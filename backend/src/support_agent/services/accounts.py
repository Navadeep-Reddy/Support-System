from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import Session

from support_agent.models import Customer, PasswordResetRequest
from support_agent.repositories.accounts import AccountRepository
from support_agent.schemas.account import PaymentData, ResetPayload, ResetResult, SubscriptionData


class AccountError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AccountService:
    """Account operations for a customer ID supplied by trusted backend context.

    The caller owns the transaction: commit the reset and approval outcome together,
    or roll them both back. The approval row remains locked until that transaction ends.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = AccountRepository(session)

    def current_subscription(self, customer_id: UUID) -> SubscriptionData:
        found = self.repository.subscription(customer_id)
        if found is None:
            raise AccountError("SUBSCRIPTION_NOT_FOUND", "No subscription was found.")
        subscription, plan = found
        return SubscriptionData(
            plan=plan.name, monthly_price=plan.monthly_price, currency=plan.currency,
            status=subscription.status, period_start=subscription.billing_period_start,
            period_end=subscription.billing_period_end,
        )

    def latest_payment(self, customer_id: UUID) -> PaymentData:
        payment = self.repository.latest_payment(customer_id)
        if payment is None:
            raise AccountError("PAYMENT_NOT_FOUND", "No payment record was found.")
        return PaymentData(
            amount=payment.amount, currency=payment.currency, date=payment.occurred_at,
            status=payment.status, failure_reason=payment.failure_reason,
        )

    def prepare_reset(self, customer_id: UUID, action_id: UUID) -> ResetPayload:
        customer = self.session.get(Customer, customer_id)
        if customer is None:
            raise AccountError("NOT_FOUND", "The customer was not found.")
        return ResetPayload(action_id=action_id, account_display_name=customer.display_name)

    def execute_reset(self, customer_id: UUID, action_id: UUID) -> ResetResult:
        approval = self.repository.owned_approval_for_update(customer_id, action_id)
        if approval is None:
            raise AccountError("NOT_FOUND", "The action was not found.")
        try:
            payload = ResetPayload.model_validate(approval.validated_payload)
        except ValidationError:
            raise AccountError("INVALID_ACTION", "The stored action is invalid.") from None
        customer = self.session.get(Customer, customer_id)
        if (approval.action_type != "request_password_reset" or payload.action_id != action_id
                or customer is None or payload.account_display_name != customer.display_name):
            raise AccountError("INVALID_ACTION", "The stored action is invalid.")
        if approval.status == "executed":
            try:
                return ResetResult.model_validate(approval.execution_result)
            except ValidationError:
                raise AccountError("INVALID_ACTION", "The stored result is invalid.") from None
        if approval.status != "approved" or approval.decided_at is None:
            raise AccountError("APPROVAL_REQUIRED", "An approved action is required.")
        reset = PasswordResetRequest(customer_id=customer_id, action_id=action_id)
        self.session.add(reset)
        self.session.flush()
        result = ResetResult(
            request_id=reset.id, reset_url=f"https://example.invalid/reset/{reset.id}"
        )
        approval.status = "executed"
        approval.execution_result = result.model_dump(mode="json")
        self.session.flush()
        return result
