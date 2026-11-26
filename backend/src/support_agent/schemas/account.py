from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SubscriptionData(BaseModel):
    plan: str
    monthly_price: Decimal
    currency: str
    status: str
    billing_cycle: Literal["monthly"] = "monthly"
    period_start: datetime | None
    period_end: datetime | None


class PaymentData(BaseModel):
    amount: Decimal
    currency: str
    date: datetime
    status: str
    failure_reason: str | None


class ResetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    action_type: Literal["request_password_reset"] = "request_password_reset"
    account_display_name: str


class ResetResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    status: Literal["requested"] = "requested"
    reset_url: str
    simulated: Literal[True] = True
