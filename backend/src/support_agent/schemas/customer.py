from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    handle: str
    display_name: str


class CustomerList(BaseModel):
    items: list[CustomerResponse]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: UUID
