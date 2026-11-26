from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from support_agent.models.base import Base, UUIDPrimaryKeyMixin


class Customer(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "customers"

    handle: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)

    def __repr__(self) -> str:
        return f"Customer(id={self.id}, handle={self.handle!r})"
