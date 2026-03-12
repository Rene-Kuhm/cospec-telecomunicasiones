import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ticket_not_found
from app.database import get_db
from app.dependencies import get_admin_or_tech, get_any_role, get_current_user
from app.models.appointment import Appointment
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.appointment import AppointmentOut, AppointmentRequest
from app.schemas.common import ApiResponse, PaginatedResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["appointments"])


@router.get("/{ticket_id}/appointments", response_model=ApiResponse[PaginatedResponse[AppointmentOut]])
async def list_appointments(
    ticket_id: uuid.UUID,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_any_role),
) -> ApiResponse[PaginatedResponse[AppointmentOut]]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    count_result = await db.execute(
        select(func.count()).select_from(Appointment).where(Appointment.ticket_id == ticket_id)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Appointment)
        .where(Appointment.ticket_id == ticket_id)
        .order_by(Appointment.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(result.scalars().all())
    out = [AppointmentOut.model_validate(a) for a in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.post("/{ticket_id}/appointments", response_model=ApiResponse[AppointmentOut])
async def create_appointment(
    ticket_id: uuid.UUID,
    body: AppointmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_or_tech),
) -> ApiResponse[AppointmentOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    appointment = Appointment(
        ticket_id=ticket_id,
        window_start=body.window_start,
        window_end=body.window_end,
        status=str(body.status),
        updated_by=current_user.id,
    )
    db.add(appointment)
    await db.flush()
    await db.refresh(appointment)

    # Update ticket window
    ticket.window_start = body.window_start
    ticket.window_end = body.window_end
    db.add(ticket)
    await db.flush()

    return ApiResponse.ok(AppointmentOut.model_validate(appointment))
