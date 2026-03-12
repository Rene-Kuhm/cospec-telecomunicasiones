import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.enums import TicketEventType
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError, ticket_not_found
from app.core.enums import UserRole
from app.database import get_db
from app.dependencies import get_admin_or_tech, get_any_role, get_current_user
from app.models.attachment import Attachment
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.attachment import AttachmentOut, AttachmentUploadRequest, AttachmentUploadResponse
from app.schemas.common import ApiResponse, PaginatedResponse
from app.services.storage import storage_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["attachments"])


def _to_attachment_out(attachment: Attachment) -> AttachmentOut:
    download_url, url_expires_at = storage_service.generate_download_presigned_url(
        attachment.storage_key
    )
    return AttachmentOut(
        id=attachment.id,
        ticket_id=attachment.ticket_id,
        uploader_id=attachment.uploader_id,
        original_filename=attachment.original_filename,
        content_type=attachment.content_type,
        type=attachment.type,
        created_at=attachment.created_at,
        download_url=download_url,
        url_expires_at=url_expires_at,
    )


@router.get("/{ticket_id}/attachments", response_model=ApiResponse[PaginatedResponse[AttachmentOut]])
async def list_attachments(
    ticket_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_any_role),
) -> ApiResponse[PaginatedResponse[AttachmentOut]]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    count_result = await db.execute(
        select(func.count())
        .select_from(Attachment)
        .where(and_(Attachment.ticket_id == ticket_id, Attachment.deleted_at.is_(None)))
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Attachment)
        .where(and_(Attachment.ticket_id == ticket_id, Attachment.deleted_at.is_(None)))
        .order_by(Attachment.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(result.scalars().all())
    out = [_to_attachment_out(a) for a in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.post("/{ticket_id}/attachments", response_model=ApiResponse[AttachmentUploadResponse])
async def create_attachment(
    ticket_id: uuid.UUID,
    body: AttachmentUploadRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AttachmentUploadResponse]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    # Validate content type
    if body.content_type not in settings.ATTACHMENT_ALLOWED_TYPES:
        raise ValidationError(
            code="INVALID_CONTENT_TYPE",
            message=f"Content type '{body.content_type}' is not allowed",
        )

    # Check attachment count per ticket
    count_result = await db.execute(
        select(func.count())
        .select_from(Attachment)
        .where(and_(Attachment.ticket_id == ticket_id, Attachment.deleted_at.is_(None)))
    )
    current_count = count_result.scalar_one()
    if current_count >= settings.ATTACHMENT_MAX_PER_TICKET:
        raise ValidationError(
            code="MAX_ATTACHMENTS_REACHED",
            message=f"Maximum of {settings.ATTACHMENT_MAX_PER_TICKET} attachments allowed per ticket",
        )

    attachment_id = uuid.uuid4()
    storage_key = storage_service.build_attachment_key(
        ticket_id=ticket_id,
        attachment_id=attachment_id,
        filename=body.original_filename,
    )

    upload_url, download_url = storage_service.generate_upload_presigned_url(
        key=storage_key,
        content_type=body.content_type,
    )
    _, url_expires_at = storage_service.generate_download_presigned_url(storage_key)

    attachment = Attachment(
        id=attachment_id,
        ticket_id=ticket_id,
        uploader_id=current_user.id,
        storage_key=storage_key,
        original_filename=body.original_filename,
        content_type=body.content_type,
        type=str(body.type),
    )
    db.add(attachment)
    await db.flush()

    await repo.create_event(
        ticket_id=ticket_id,
        actor_id=current_user.id,
        event_type=TicketEventType.EVIDENCE_ADDED,
        payload={"attachment_id": str(attachment_id), "filename": body.original_filename},
    )

    return ApiResponse.ok(
        AttachmentUploadResponse(
            id=attachment_id,
            upload_url=upload_url,
            download_url=download_url,
            url_expires_at=url_expires_at,
        )
    )


@router.delete("/{ticket_id}/attachments/{attachment_id}", response_model=ApiResponse[dict])
async def delete_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    result = await db.execute(
        select(Attachment).where(
            and_(
                Attachment.id == attachment_id,
                Attachment.ticket_id == ticket_id,
                Attachment.deleted_at.is_(None),
            )
        )
    )
    attachment = result.scalar_one_or_none()
    if attachment is None:
        raise NotFoundError(code="ATTACHMENT_NOT_FOUND", message="Attachment not found")

    # Only uploader, admin, or assigned tech can delete
    if (
        current_user.role != UserRole.ADMIN
        and attachment.uploader_id != current_user.id
    ):
        raise ForbiddenError(code="FORBIDDEN", message="Cannot delete another user's attachment")

    from datetime import UTC, datetime  # noqa: PLC0415

    attachment.deleted_at = datetime.now(UTC)
    db.add(attachment)
    await db.flush()

    # Soft-delete storage (mark deleted, actual cleanup can be async)
    try:
        storage_service.delete_object(attachment.storage_key)
    except Exception:
        log.warning("storage_delete_failed", key=attachment.storage_key)

    await repo.create_event(
        ticket_id=ticket_id,
        actor_id=current_user.id,
        event_type=TicketEventType.EVIDENCE_DELETED,
        payload={"attachment_id": str(attachment_id)},
    )

    return ApiResponse.ok({"message": "Attachment deleted"})
