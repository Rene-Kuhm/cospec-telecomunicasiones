import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.common import PaginatedResponse


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_id: uuid.UUID
    body: str
    attachment_id: uuid.UUID | None
    created_at: datetime


class MessageCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    body: str
    attachment_id: uuid.UUID | None = None


PaginatedMessages = PaginatedResponse[MessageOut]
