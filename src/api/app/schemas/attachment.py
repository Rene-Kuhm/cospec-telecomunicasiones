import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import AttachmentType
from app.schemas.common import PaginatedResponse


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    uploader_id: uuid.UUID
    original_filename: str
    content_type: str
    type: AttachmentType
    created_at: datetime
    # Generated at response time — never storage_key
    download_url: str
    url_expires_at: datetime


class AttachmentUploadRequest(BaseModel):
    original_filename: str
    content_type: str
    type: AttachmentType = AttachmentType.DOC


class AttachmentUploadResponse(BaseModel):
    id: uuid.UUID
    upload_url: str
    download_url: str
    url_expires_at: datetime


PaginatedAttachments = PaginatedResponse[AttachmentOut]
