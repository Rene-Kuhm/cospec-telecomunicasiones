import uuid
from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TicketPriority, TicketStatus, UserRole
from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError, ticket_not_found
from app.database import get_db
from app.dependencies import get_admin, get_any_role, get_current_user
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.ticket import (
    TicketCreateRequest,
    TicketOut,
    TicketPatchRequest,
)
from app.services.ticket import TicketService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=ApiResponse[TicketOut])
async def create_ticket(
    body: TicketCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[TicketOut]:
    if current_user.role == UserRole.CUSTOMER and not current_user.email_verified:
        raise ValidationError(
            code="EMAIL_NOT_VERIFIED",
            message="Please verify your email before creating tickets",
        )
    if current_user.role == UserRole.TECH:
        raise ForbiddenError(
            code="FORBIDDEN",
            message="Technicians cannot create tickets",
        )

    service = TicketService()
    ticket = await service.create(
        data=body,
        customer_id=current_user.id if current_user.role == UserRole.CUSTOMER else current_user.id,
        db=db,
    )
    return ApiResponse.ok(TicketOut.model_validate(ticket))


@router.get("", response_model=ApiResponse[PaginatedResponse[TicketOut]])
async def list_tickets(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: TicketStatus | None = Query(None),
    priority: TicketPriority | None = Query(None),
    category: str | None = Query(None),
    zone: str | None = Query(None),
    assigned_to: uuid.UUID | None = Query(None),
    customer_id: uuid.UUID | None = Query(None),
    sla_breached: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    updated_after: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_any_role),
) -> ApiResponse[PaginatedResponse[TicketOut]]:
    repo = TicketRepository(db)
    items, total = await repo.list_tickets(
        page=page,
        limit=limit,
        role=current_user.role,
        user_id=current_user.id,
        status=str(status) if status else None,
        priority=str(priority) if priority else None,
        category=category,
        zone=zone,
        assigned_to=assigned_to,
        customer_id=customer_id,
        sla_breached=sla_breached,
        date_from=date_from,
        date_to=date_to,
        updated_after=updated_after,
    )
    out = [TicketOut.model_validate(t) for t in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.get("/{ticket_id}", response_model=ApiResponse[TicketOut])
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_any_role),
) -> ApiResponse[TicketOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    # RBAC: techs only see their assigned tickets, customers only their own
    if current_user.role == UserRole.TECH and ticket.assigned_to != current_user.id:
        raise ForbiddenError()
    if current_user.role == UserRole.CUSTOMER and ticket.customer_id != current_user.id:
        raise ForbiddenError()

    return ApiResponse.ok(TicketOut.model_validate(ticket))


@router.patch("/{ticket_id}", response_model=ApiResponse[TicketOut])
async def patch_ticket(
    ticket_id: uuid.UUID,
    body: TicketPatchRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[TicketOut]:
    repo = TicketRepository(db)
    ticket = await repo.get_by_id(ticket_id)
    if ticket is None or ticket.deleted_at is not None:
        raise ticket_not_found(str(ticket_id))

    update_data = body.model_dump(exclude_none=True)
    updated = await repo.update(ticket, **update_data)
    return ApiResponse.ok(TicketOut.model_validate(updated))
