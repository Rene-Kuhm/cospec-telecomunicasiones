import uuid

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ticket_not_found
from app.database import get_db
from app.dependencies import get_admin
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.common import ApiResponse
from app.schemas.ticket import TicketOut
from app.services.ticket import TicketService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["assignments"])


class AssignRequest(BaseModel):
    tech_id: uuid.UUID


@router.post("/{ticket_id}/assign", response_model=ApiResponse[TicketOut])
async def assign_ticket(
    ticket_id: uuid.UUID,
    body: AssignRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin),
) -> ApiResponse[TicketOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    service = TicketService()
    updated = await service.assign(ticket=ticket, tech_id=body.tech_id, actor=admin, db=db)
    return ApiResponse.ok(TicketOut.model_validate(updated))


@router.post("/{ticket_id}/auto-assign", response_model=ApiResponse[TicketOut])
async def auto_assign_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[TicketOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    service = TicketService()
    updated = await service.auto_assign(ticket=ticket, db=db)
    return ApiResponse.ok(TicketOut.model_validate(updated))
