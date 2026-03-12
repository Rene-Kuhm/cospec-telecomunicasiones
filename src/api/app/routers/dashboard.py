import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TicketStatus, UserRole
from app.database import get_db
from app.dependencies import get_admin, get_tech
from app.models.appointment import Appointment
from app.models.checklist import ChecklistItem
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.dashboard import (
    AdminDashboard,
    NextAppointment,
    PendingChecklist,
    SLABreachTicket,
    TechDashboard,
    TechProductivity,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/admin", response_model=ApiResponse[AdminDashboard])
async def admin_dashboard(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[AdminDashboard]:
    # Tickets by status
    status_result = await db.execute(
        select(Ticket.status, func.count().label("cnt"))
        .where(Ticket.deleted_at.is_(None))
        .group_by(Ticket.status)
    )
    tickets_by_status: dict[str, int] = {row.status: row.cnt for row in status_result}

    # SLA breaches
    now = datetime.now(UTC)
    breach_result = await db.execute(
        select(Ticket).where(
            and_(
                Ticket.deleted_at.is_(None),
                Ticket.sla_due_at.isnot(None),
                Ticket.sla_due_at < now,
                Ticket.status.notin_([TicketStatus.RESUELTO, TicketStatus.CERRADO]),
            )
        ).limit(50)
    )
    breach_tickets = list(breach_result.scalars().all())
    sla_breach_list = [
        SLABreachTicket(
            id=t.id,
            title=t.title,
            status=t.status,
            priority=t.priority,
            sla_due_at=t.sla_due_at,
            assigned_to=t.assigned_to,
        )
        for t in breach_tickets
    ]

    # Tech productivity
    tech_result = await db.execute(
        select(User).where(
            and_(User.role == UserRole.TECH, User.deleted_at.is_(None), User.active.is_(True))
        )
    )
    techs = list(tech_result.scalars().all())

    productivity_list: list[TechProductivity] = []
    for tech in techs:
        assigned_result = await db.execute(
            select(func.count()).select_from(Ticket).where(
                and_(Ticket.assigned_to == tech.id, Ticket.deleted_at.is_(None))
            )
        )
        resolved_result = await db.execute(
            select(func.count()).select_from(Ticket).where(
                and_(
                    Ticket.assigned_to == tech.id,
                    Ticket.status == TicketStatus.RESUELTO,
                    Ticket.deleted_at.is_(None),
                )
            )
        )
        closed_result = await db.execute(
            select(func.count()).select_from(Ticket).where(
                and_(
                    Ticket.assigned_to == tech.id,
                    Ticket.status == TicketStatus.CERRADO,
                    Ticket.deleted_at.is_(None),
                )
            )
        )
        productivity_list.append(
            TechProductivity(
                tech_id=tech.id,
                tech_name=tech.name,
                tickets_assigned=assigned_result.scalar_one(),
                tickets_resolved=resolved_result.scalar_one(),
                tickets_closed=closed_result.scalar_one(),
                avg_resolution_hours=None,
            )
        )

    return ApiResponse.ok(
        AdminDashboard(
            tickets_by_status=tickets_by_status,
            sla_breach_count=len(breach_tickets),
            sla_breach_tickets=sla_breach_list,
            tech_productivity=productivity_list,
        )
    )


@router.get("/tech", response_model=ApiResponse[TechDashboard])
async def tech_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_tech),
) -> ApiResponse[TechDashboard]:
    # My tickets by status
    status_result = await db.execute(
        select(Ticket.status, func.count().label("cnt"))
        .where(
            and_(
                Ticket.assigned_to == current_user.id,
                Ticket.deleted_at.is_(None),
            )
        )
        .group_by(Ticket.status)
    )
    my_tickets_by_status: dict[str, int] = {row.status: row.cnt for row in status_result}

    # Next appointments (upcoming)
    now = datetime.now(UTC)
    appt_result = await db.execute(
        select(Appointment, Ticket)
        .join(Ticket, Appointment.ticket_id == Ticket.id)
        .where(
            and_(
                Ticket.assigned_to == current_user.id,
                Appointment.window_start >= now,
                Appointment.status.notin_(["cancelled"]),
                Ticket.deleted_at.is_(None),
            )
        )
        .order_by(Appointment.window_start)
        .limit(10)
    )
    next_appointments: list[NextAppointment] = []
    for appt, ticket in appt_result:
        next_appointments.append(
            NextAppointment(
                ticket_id=ticket.id,
                ticket_title=ticket.title,
                window_start=appt.window_start,
                window_end=appt.window_end,
                address=ticket.address,
            )
        )

    # Pending checklists
    checklist_result = await db.execute(
        select(
            Ticket.id,
            Ticket.title,
            func.count(ChecklistItem.id).filter(ChecklistItem.status == "pending").label("pending"),
            func.count(ChecklistItem.id).label("total"),
        )
        .join(ChecklistItem, ChecklistItem.ticket_id == Ticket.id)
        .where(
            and_(
                Ticket.assigned_to == current_user.id,
                Ticket.deleted_at.is_(None),
                Ticket.status.notin_([TicketStatus.CERRADO, TicketStatus.RESUELTO]),
            )
        )
        .group_by(Ticket.id, Ticket.title)
        .having(func.count(ChecklistItem.id).filter(ChecklistItem.status == "pending") > 0)
        .limit(20)
    )
    pending_checklists: list[PendingChecklist] = []
    for row in checklist_result:
        pending_checklists.append(
            PendingChecklist(
                ticket_id=row.id,
                ticket_title=row.title,
                pending_items=row.pending,
                total_items=row.total,
            )
        )

    return ApiResponse.ok(
        TechDashboard(
            my_tickets_by_status=my_tickets_by_status,
            next_appointments=next_appointments,
            pending_checklists=pending_checklists,
        )
    )
