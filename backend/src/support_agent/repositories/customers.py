from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from support_agent.models.customer import Customer


class CustomerRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_customers(self) -> list[Customer]:
        return list(self.session.scalars(select(Customer).order_by(Customer.handle)))

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return self.session.get(Customer, customer_id)
