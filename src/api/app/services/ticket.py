import uuid
from datetime import UTC, datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

import structlog
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    GeocodingStatus,
    TICKET_TRANSITIONS,
    TicketEventType,
    TicketStatus,
    UserRole,
)
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ValidationError,
    assignment_no_candidate,
    checklist_incomplete,
    invalid_transition,
    no_evidence,
    ticket_not_found,
)
from app.models.checklist import ChecklistItem
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.ticket import TicketRepository
from app.repositories.user import UserRepository
from app.schemas.ticket import TicketCreateRequest

log = structlog.get_logger(__name__)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points."""
    r = 6371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * r * asin(sqrt(a))


class TicketService:
    async def create(
        self,
        data: TicketCreateRequest,
        customer_id: uuid.UUID,
        db: AsyncSession,
    ) -> Ticket:
        ticket_repo = TicketRepository(db)
        now = datetime.now(UTC)

        sla_due_at = await ticket_repo.get_sla_due_at(
            category=data.category,
            priority=str(data.priority),
            created_at=now,
            db=db,
        )

        ticket = await ticket_repo.create(
            title=data.title,
            description=data.description,
            category=data.category,
            priority=str(data.priority),
            status=TicketStatus.ABIERTO,
            sla_due_at=sla_due_at,
            geocoding_status=GeocodingStatus.PENDING if data.address else GeocodingStatus.FAILED,
            address=data.address,
            window_start=data.window_start,
            window_end=data.window_end,
            customer_id=customer_id,
        )

        # Populate checklist from category template
        await self._create_checklist_from_category(ticket.id, data.category, db)

        # Log creation event
        await ticket_repo.create_event(
            ticket_id=ticket.id,
            actor_id=customer_id,
            event_type=TicketEventType.CREATED,
            payload={"title": data.title, "category": data.category, "priority": str(data.priority)},
        )

        # Queue geocoding if address provided
        if data.address:
            await self._queue_geocoding(ticket)

        log.info("ticket_created", ticket_id=str(ticket.id), category=data.category)
        return ticket

    async def transition_status(
        self,
        ticket: Ticket,
        next_status: TicketStatus,
        actor: User,
        timestamp: datetime | None,
        db: AsyncSession,
    ) -> Ticket:
        ticket_repo = TicketRepository(db)
        current_status = TicketStatus(ticket.status)

        allowed = TICKET_TRANSITIONS.get(current_status, [])
        if next_status not in allowed:
            raise invalid_transition(str(current_status), str(next_status))

        # Closing validations
        if next_status == TicketStatus.CERRADO:
            checklist_ok = await ticket_repo.is_checklist_complete(ticket.id)
            if not checklist_ok:
                raise checklist_incomplete()
            has_ev = await ticket_repo.has_evidence(ticket.id)
            if not has_ev:
                raise no_evidence()

        old_status = ticket.status
        ticket.status = str(next_status)
        if next_status == TicketStatus.CERRADO:
            ticket.closed_at = timestamp or datetime.now(UTC)
        elif next_status == TicketStatus.RESUELTO:
            ticket.closed_at = timestamp or datetime.now(UTC)

        db.add(ticket)
        await db.flush()
        await db.refresh(ticket)

        await ticket_repo.create_event(
            ticket_id=ticket.id,
            actor_id=actor.id,
            event_type=TicketEventType.STATUS_CHANGED,
            payload={"from": old_status, "to": str(next_status)},
        )

        # Broadcast SSE
        await self._broadcast_status_change(ticket, actor)

        log.info(
            "ticket_status_changed",
            ticket_id=str(ticket.id),
            from_status=old_status,
            to_status=str(next_status),
        )
        return ticket

    async def assign(
        self,
        ticket: Ticket,
        tech_id: uuid.UUID,
        actor: User,
        db: AsyncSession,
    ) -> Ticket:
        ticket_repo = TicketRepository(db)
        user_repo = UserRepository(db)

        tech = await user_repo.get_by_id(tech_id)
        if tech is None or tech.role != UserRole.TECH or not tech.active:
            raise NotFoundError(code="TECH_NOT_FOUND", message="Technician not found or inactive")

        ticket.assigned_to = tech_id
        ticket.status = TicketStatus.ASIGNADO
        db.add(ticket)
        await db.flush()
        await db.refresh(ticket)

        await ticket_repo.create_event(
            ticket_id=ticket.id,
            actor_id=actor.id,
            event_type=TicketEventType.ASSIGNED,
            payload={"tech_id": str(tech_id), "tech_name": tech.name},
        )

        await self._broadcast_assignment(ticket, tech)
        log.info("ticket_assigned", ticket_id=str(ticket.id), tech_id=str(tech_id))
        return ticket

    async def auto_assign(self, ticket: Ticket, db: AsyncSession) -> Ticket:
        """
        Auto-assignment scoring algorithm:
        - Skills match with category required_skills: +10 per matching skill
        - Zone match: +20 if tech zone matches ticket zone (derived from category or address)
        - Active tickets count: -2 per active ticket (penalize overloaded techs)
        - Proximity (if geocoded): -0.1 * distance_km
        """
        from app.models.category import Category  # noqa: PLC0415

        cat_result = await db.execute(
            select(Category).where(Category.slug == ticket.category)
        )
        category = cat_result.scalar_one_or_none()
        required_skills: list[str] = category.required_skills if category else []

        # Get all active techs
        user_repo = UserRepository(db)
        techs, _ = await user_repo.get_techs(page=1, limit=200, active=True)

        if not techs:
            raise assignment_no_candidate()

        # Count active tickets per tech
        active_counts: dict[uuid.UUID, int] = {}
        for tech in techs:
            result = await db.execute(
                select(func.count()).select_from(Ticket).where(
                    and_(
                        Ticket.assigned_to == tech.id,
                        Ticket.status.notin_([TicketStatus.RESUELTO, TicketStatus.CERRADO]),
                        Ticket.deleted_at.is_(None),
                    )
                )
            )
            active_counts[tech.id] = result.scalar_one()

        best_tech: User | None = None
        best_score = float("-inf")

        for tech in techs:
            score = 0.0
            # Skills match
            for skill in required_skills:
                if skill in (tech.skills or []):
                    score += 10.0

            # Zone match (use category's default or ticket's zone)
            if tech.zone and ticket.address:
                # Naive zone match: zone keyword in address
                if tech.zone.lower() in ticket.address.lower():
                    score += 20.0

            # Penalize for active tickets
            score -= active_counts.get(tech.id, 0) * 2.0

            # Proximity bonus
            if ticket.lat and ticket.lon:
                # No tech lat/lon stored — skip proximity for now
                pass

            if score > best_score:
                best_score = score
                best_tech = tech

        if best_tech is None:
            raise assignment_no_candidate()

        # Use a system actor (no specific user)
        ticket_repo = TicketRepository(db)
        ticket.assigned_to = best_tech.id
        ticket.status = TicketStatus.ASIGNADO
        db.add(ticket)
        await db.flush()
        await db.refresh(ticket)

        await ticket_repo.create_event(
            ticket_id=ticket.id,
            actor_id=None,
            event_type=TicketEventType.ASSIGNED,
            payload={
                "tech_id": str(best_tech.id),
                "tech_name": best_tech.name,
                "auto": True,
                "score": best_score,
            },
        )

        await self._broadcast_assignment(ticket, best_tech)
        log.info("ticket_auto_assigned", ticket_id=str(ticket.id), tech_id=str(best_tech.id), score=best_score)
        return ticket

    async def _create_checklist_from_category(
        self,
        ticket_id: uuid.UUID,
        category_slug: str,
        db: AsyncSession,
    ) -> None:
        from app.models.category import Category  # noqa: PLC0415

        result = await db.execute(
            select(Category).where(Category.slug == category_slug)
        )
        cat = result.scalar_one_or_none()
        if cat is None or not cat.default_checklist:
            return

        for checklist_entry in cat.default_checklist:
            item_text = checklist_entry if isinstance(checklist_entry, str) else checklist_entry.get("item", "")
            if item_text:
                db.add(ChecklistItem(
                    ticket_id=ticket_id,
                    item=item_text,
                    status="pending",
                ))
        await db.flush()

    async def _queue_geocoding(self, ticket: Ticket) -> None:
        try:
            from app.services.sse import broadcaster  # noqa: PLC0415
            # In production, queue to ARQ. Here we just log.
            log.info("geocoding_queued", ticket_id=str(ticket.id), address=ticket.address)
        except Exception:
            log.warning("failed_to_queue_geocoding", ticket_id=str(ticket.id))

    async def _broadcast_status_change(self, ticket: Ticket, actor: User) -> None:
        try:
            from app.services.sse import broadcaster  # noqa: PLC0415
            await broadcaster.broadcast_to_role(
                role=UserRole.ADMIN,
                event_type="ticket.status_changed",
                data={"ticket_id": str(ticket.id), "status": ticket.status},
            )
            if ticket.customer_id:
                await broadcaster.broadcast_to_user(
                    user_id=ticket.customer_id,
                    event_type="ticket.status_changed",
                    data={"ticket_id": str(ticket.id), "status": ticket.status},
                )
        except Exception:
            log.warning("sse_broadcast_failed", ticket_id=str(ticket.id))

    async def _broadcast_assignment(self, ticket: Ticket, tech: User) -> None:
        try:
            from app.services.sse import broadcaster  # noqa: PLC0415
            await broadcaster.broadcast_to_user(
                user_id=tech.id,
                event_type="ticket.assigned",
                data={"ticket_id": str(ticket.id), "title": ticket.title},
            )
        except Exception:
            log.warning("sse_broadcast_failed", ticket_id=str(ticket.id))
