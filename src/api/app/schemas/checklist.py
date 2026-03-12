import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ChecklistItemStatus


class ChecklistItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    item: str
    status: ChecklistItemStatus
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ChecklistUpdateItem(BaseModel):
    id: uuid.UUID
    status: ChecklistItemStatus
