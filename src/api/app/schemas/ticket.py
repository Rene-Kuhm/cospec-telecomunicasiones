import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.core.enums import GeocodingStatus, TicketPriority, TicketStatus
from app.schemas.common import PaginatedResponse


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str
    category: str
    priority: TicketPriority
    status: TicketStatus
    sla_due_at: datetime | None
    sla_override: datetime | None
    geocoding_status: GeocodingStatus
    address: str | None
    lat: float | None
    lon: float | None
    window_start: datetime | None
    window_end: datetime | None
    customer_id: uuid.UUID
    assigned_to: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    @computed_field  # type: ignore[misc]
    @property
    def sla_breached(self) -> bool:
        effective_due = self.sla_override or self.sla_due_at
        if effective_due is None:
            return False
        if self.status in (TicketStatus.RESUELTO, TicketStatus.CERRADO):
            return False
        return datetime.now(UTC) > effective_due

    @computed_field  # type: ignore[misc]
    @property
    def navigation_url(self) -> str | None:
        if self.lat is not None and self.lon is not None:
            return f"https://www.google.com/maps/dir/?api=1&destination={self.lat},{self.lon}"
        return None


class TicketCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str
    description: str
    category: str
    priority: TicketPriority = TicketPriority.MEDIUM
    address: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


class TicketPatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = None
    description: str | None = None
    category: str | None = None
    priority: TicketPriority | None = None
    address: str | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None
    sla_override: datetime | None = None


class StatusChangeRequest(BaseModel):
    status: TicketStatus
    timestamp: datetime | None = None


PaginatedTickets = PaginatedResponse[TicketOut]
