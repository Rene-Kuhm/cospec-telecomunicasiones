import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import ExportKind, ExportStatus
from app.schemas.common import PaginatedResponse


class ExportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    period_date: datetime
    kind: ExportKind
    status: ExportStatus
    generated_at: datetime | None
    triggered_by: uuid.UUID | None
    error_message: str | None
    created_at: datetime
    # Generated only when status == completed
    download_url: str | None = None
    url_expires_at: datetime | None = None


class ExportRunRequest(BaseModel):
    kind: ExportKind
    period_date: datetime


PaginatedExports = PaginatedResponse[ExportOut]
