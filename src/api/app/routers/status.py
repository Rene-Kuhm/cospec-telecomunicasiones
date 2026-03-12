import uuid

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ticket_not_found
from app.database import get_db
from app.dependencies import get_admin_or_tech, get_current_user
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.common import ApiResponse
from app.schemas.ticket import StatusChangeRequest, TicketOut
from app.services.ticket import TicketService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["status"])


@router.post("/{ticket_id}/status", response_model=ApiResponse[TicketOut])
async def change_status(
    ticket_id: uuid.UUID,
    body: StatusChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_or_tech),
) -> ApiResponse[TicketOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    service = TicketService()
    updated = await service.transition_status(
        ticket=ticket,
        next_status=body.status,
        actor=current_user,
        timestamp=body.timestamp,
        db=db,
    )
    return ApiResponse.ok(TicketOut.model_validate(updated))
