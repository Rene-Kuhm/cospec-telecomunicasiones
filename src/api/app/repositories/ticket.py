import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.enums import TicketEventType, TicketStatus, UserRole
from app.models.attachment import Attachment
from app.models.checklist import ChecklistItem
from app.models.ticket import Ticket
from app.models.ticket_event import TicketEvent
from app.repositories.base import BaseRepository


class TicketRepository(BaseRepository[Ticket]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Ticket, session)

    async def get_with_events(self, ticket_id: uuid.UUID) -> Ticket | None:
        result = await self.session.execute(
            select(Ticket)
            .options(selectinload(Ticket.ticket_events))
            .where(and_(Ticket.id == ticket_id, Ticket.deleted_at.is_(None)))
        )
        return result.scalar_one_or_none()

    async def list_tickets(
        self,
        page: int = 1,
        limit: int = 20,
        role: str = UserRole.ADMIN,
        user_id: uuid.UUID | None = None,
        status: str | None = None,
        priority: str | None = None,
        category: str | None = None,
        zone: str | None = None,
        assigned_to: uuid.UUID | None = None,
        customer_id: uuid.UUID | None = None,
        sla_breached: bool | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        updated_after: datetime | None = None,
    ) -> tuple[list[Ticket], int]:
        conditions: list[Any] = [Ticket.deleted_at.is_(None)]

        # RBAC scoping
        if role == UserRole.TECH and user_id is not None:
            conditions.append(Ticket.assigned_to == user_id)
        elif role == UserRole.CUSTOMER and user_id is not None:
            conditions.append(Ticket.customer_id == user_id)

        if status is not None:
            conditions.append(Ticket.status == status)
        if priority is not None:
            conditions.append(Ticket.priority == priority)
        if category is not None:
            conditions.append(Ticket.category == category)
        if assigned_to is not None:
            conditions.append(Ticket.assigned_to == assigned_to)
        if customer_id is not None:
            conditions.append(Ticket.customer_id == customer_id)
        if date_from is not None:
            conditions.append(Ticket.created_at >= date_from)
        if date_to is not None:
            conditions.append(Ticket.created_at <= date_to)
        if updated_after is not None:
            conditions.append(Ticket.updated_at > updated_after)

        if sla_breached is True:
            now = datetime.now(UTC)
            conditions.append(
                and_(
                    Ticket.sla_due_at.isnot(None),
                    Ticket.sla_due_at < now,
                    Ticket.status.notin_([TicketStatus.RESUELTO, TicketStatus.CERRADO]),
                )
            )
        elif sla_breached is False:
            now = datetime.now(UTC)
            conditions.append(
                or_(
                    Ticket.sla_due_at.is_(None),
                    Ticket.sla_due_at >= now,
                    Ticket.status.in_([TicketStatus.RESUELTO, TicketStatus.CERRADO]),
                )
            )

        where_clause = and_(*conditions)
        count_query = select(func.count()).select_from(Ticket).where(where_clause)
        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = (
            select(Ticket)
            .where(where_clause)
            .order_by(Ticket.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        result = await self.session.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def create_event(
        self,
        ticket_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        event_type: TicketEventType,
        payload: dict[str, Any],
    ) -> TicketEvent:
        event = TicketEvent(
            ticket_id=ticket_id,
            actor_id=actor_id,
            type=str(event_type),
            payload=payload,
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def get_checklist(self, ticket_id: uuid.UUID) -> list[ChecklistItem]:
        result = await self.session.execute(
            select(ChecklistItem)
            .where(ChecklistItem.ticket_id == ticket_id)
            .order_by(ChecklistItem.created_at)
        )
        return list(result.scalars().all())

    async def update_checklist_item(
        self,
        item_id: uuid.UUID,
        status: str,
        updated_by: uuid.UUID,
    ) -> ChecklistItem | None:
        result = await self.session.execute(
            select(ChecklistItem).where(ChecklistItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        item.status = status
        item.updated_by = updated_by
        item.updated_at = datetime.now(UTC)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def is_checklist_complete(self, ticket_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(ChecklistItem)
            .where(
                and_(
                    ChecklistItem.ticket_id == ticket_id,
                    ChecklistItem.status == "pending",
                )
            )
        )
        pending_count = result.scalar_one()
        return pending_count == 0

    async def has_evidence(self, ticket_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(func.count())
            .select_from(Attachment)
            .where(
                and_(
                    Attachment.ticket_id == ticket_id,
                    Attachment.deleted_at.is_(None),
                )
            )
        )
        count = result.scalar_one()
        return count > 0

    async def get_sla_due_at(
        self,
        category: str,
        priority: str,
        created_at: datetime,
        db: AsyncSession,
    ) -> datetime:
        from datetime import timedelta  # noqa: PLC0415

        from app.config import settings  # noqa: PLC0415
        from app.models.category import Category  # noqa: PLC0415
        from app.models.sla_rule import SLARule  # noqa: PLC0415

        # Try to find category-specific SLA rule
        result = await db.execute(
            select(SLARule)
            .join(Category, SLARule.category_id == Category.id)
            .where(
                and_(
                    Category.slug == category,
                    SLARule.priority == priority,
                )
            )
        )
        sla_rule = result.scalar_one_or_none()

        if sla_rule:
            hours = sla_rule.sla_hours
        else:
            # Fall back to defaults
            defaults = {
                "critical": settings.SLA_DEFAULT_CRITICAL_HOURS,
                "high": settings.SLA_DEFAULT_HIGH_HOURS,
                "medium": settings.SLA_DEFAULT_MEDIUM_HOURS,
                "low": settings.SLA_DEFAULT_LOW_HOURS,
            }
            hours = defaults.get(priority, settings.SLA_DEFAULT_MEDIUM_HOURS)

        return created_at + timedelta(hours=hours)
