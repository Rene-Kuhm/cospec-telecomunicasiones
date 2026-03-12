import uuid

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ticket_not_found
from app.database import get_db
from app.dependencies import get_admin_or_tech, get_any_role
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.checklist import ChecklistItemOut, ChecklistUpdateItem
from app.schemas.common import ApiResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["checklist"])


@router.get("/{ticket_id}/checklist", response_model=ApiResponse[list[ChecklistItemOut]])
async def get_checklist(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_any_role),
) -> ApiResponse[list[ChecklistItemOut]]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    items = await repo.get_checklist(ticket_id)
    out = [ChecklistItemOut.model_validate(i) for i in items]
    return ApiResponse.ok(out)


@router.patch("/{ticket_id}/checklist", response_model=ApiResponse[list[ChecklistItemOut]])
async def update_checklist(
    ticket_id: uuid.UUID,
    updates: list[ChecklistUpdateItem],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_or_tech),
) -> ApiResponse[list[ChecklistItemOut]]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    for update in updates:
        await repo.update_checklist_item(
            item_id=update.id,
            status=str(update.status),
            updated_by=current_user.id,
        )

    items = await repo.get_checklist(ticket_id)
    out = [ChecklistItemOut.model_validate(i) for i in items]
    return ApiResponse.ok(out)
