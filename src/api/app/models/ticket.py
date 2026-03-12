import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.attachment import Attachment
    from app.models.checklist import ChecklistItem
    from app.models.message import Message
    from app.models.ticket_event import TicketEvent
    from app.models.user import User


class Ticket(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="abierto", index=True)

    # SLA
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_override: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Geocoding
    geocoding_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Scheduling window
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamps
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Foreign keys
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )

    # Relationships
    customer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[customer_id],
        back_populates="tickets_as_customer",
        lazy="noload",
    )
    tech: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[assigned_to],
        back_populates="tickets_as_tech",
        lazy="noload",
    )
    ticket_events: Mapped[list["TicketEvent"]] = relationship(
        "TicketEvent",
        back_populates="ticket",
        lazy="noload",
        order_by="TicketEvent.created_at",
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="ticket",
        lazy="noload",
        order_by="Message.created_at",
    )
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment",
        back_populates="ticket",
        lazy="noload",
        order_by="Attachment.created_at",
    )
    checklists: Mapped[list["ChecklistItem"]] = relationship(
        "ChecklistItem",
        back_populates="ticket",
        lazy="noload",
        order_by="ChecklistItem.created_at",
    )
    appointments: Mapped[list["Appointment"]] = relationship(
        "Appointment",
        back_populates="ticket",
        lazy="noload",
        order_by="Appointment.created_at",
    )
