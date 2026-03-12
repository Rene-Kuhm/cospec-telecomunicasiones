import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SLABreachTicket(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    status: str
    priority: str
    sla_due_at: datetime | None
    assigned_to: uuid.UUID | None


class TechProductivity(BaseModel):
    tech_id: uuid.UUID
    tech_name: str
    tickets_assigned: int
    tickets_resolved: int
    tickets_closed: int
    avg_resolution_hours: float | None


class NextAppointment(BaseModel):
    ticket_id: uuid.UUID
    ticket_title: str
    window_start: datetime
    window_end: datetime
    address: str | None


class PendingChecklist(BaseModel):
    ticket_id: uuid.UUID
    ticket_title: str
    pending_items: int
    total_items: int


class AdminDashboard(BaseModel):
    tickets_by_status: dict[str, int]
    sla_breach_count: int
    sla_breach_tickets: list[SLABreachTicket]
    tech_productivity: list[TechProductivity]


class TechDashboard(BaseModel):
    my_tickets_by_status: dict[str, int]
    next_appointments: list[NextAppointment]
    pending_checklists: list[PendingChecklist]
