import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import AppointmentStatus
from app.schemas.common import PaginatedResponse


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    window_start: datetime
    window_end: datetime
    status: AppointmentStatus
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AppointmentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    window_start: datetime
    window_end: datetime
    status: AppointmentStatus = AppointmentStatus.PENDING


PaginatedAppointments = PaginatedResponse[AppointmentOut]
