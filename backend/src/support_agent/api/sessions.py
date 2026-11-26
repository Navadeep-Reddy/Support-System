from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from support_agent.core.database import get_db_session
from support_agent.repositories.customers import CustomerRepository
from support_agent.schemas.customer import CustomerList, CustomerResponse, LoginRequest

router = APIRouter(tags=["sessions"])
Database = Annotated[Session, Depends(get_db_session)]


def current_customer(request: Request, db: Database) -> CustomerResponse:
    try:
        customer_id = UUID(request.session.get("customer_id", ""))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=401) from None
    customer = CustomerRepository(db).get_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=401)
    return CustomerResponse.model_validate(customer)


@router.get("/customers", response_model=CustomerList)
def list_customers(db: Database) -> CustomerList:
    customers = CustomerRepository(db).list_customers()
    return CustomerList(items=[CustomerResponse.model_validate(customer) for customer in customers])


@router.post("/sessions", response_model=CustomerResponse)
def login(body: LoginRequest, request: Request, db: Database) -> CustomerResponse:
    customer = CustomerRepository(db).get_customer(body.customer_id)
    if customer is None:
        raise HTTPException(status_code=404)
    request.session.clear()
    request.session["customer_id"] = str(customer.id)
    return CustomerResponse.model_validate(customer)


@router.delete("/sessions/current", status_code=204)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)


@router.get("/me", response_model=CustomerResponse)
def me(customer: Annotated[CustomerResponse, Depends(current_customer)]) -> CustomerResponse:
    return customer
