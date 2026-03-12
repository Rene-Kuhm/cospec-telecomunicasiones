import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category


class SLARule(Base, TimestampMixin):
    __tablename__ = "sla_rules"
    __table_args__ = (UniqueConstraint("category_id", "priority", name="uq_sla_rule_category_priority"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id"),
        nullable=False,
        index=True,
    )
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, nullable=False)

    category: Mapped["Category"] = relationship("Category", back_populates="sla_rules", lazy="noload")
