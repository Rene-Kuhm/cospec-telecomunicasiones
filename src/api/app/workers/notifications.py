import uuid

import structlog

log = structlog.get_logger(__name__)


async def send_notification(
    ctx: dict,
    ticket_id: str,
    event_type: str,
    recipient_id: str,
) -> None:
    """ARQ worker task: send notification for a ticket event."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.models.ticket import Ticket  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415
    from app.services.notification import notification_service  # noqa: PLC0415

    log.info("send_notification_start", ticket_id=ticket_id, event_type=event_type, recipient_id=recipient_id)

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            from sqlalchemy import select  # noqa: PLC0415

            ticket_result = await db.execute(
                select(Ticket).where(Ticket.id == uuid.UUID(ticket_id))
            )
            ticket = ticket_result.scalar_one_or_none()
            if ticket is None:
                log.warning("notification_ticket_not_found", ticket_id=ticket_id)
                return

            recipient_result = await db.execute(
                select(User).where(User.id == uuid.UUID(recipient_id))
            )
            recipient = recipient_result.scalar_one_or_none()
            if recipient is None:
                log.warning("notification_recipient_not_found", recipient_id=recipient_id)
                return

            if event_type == "ticket_assigned":
                await notification_service.notify_ticket_assigned(ticket, recipient)
            elif event_type == "ticket_status_changed":
                await notification_service.notify_ticket_status_changed(
                    ticket, ticket.status, recipient
                )
            elif event_type == "ticket_created":
                await notification_service.notify_ticket_created(ticket, recipient)
            else:
                log.warning("unknown_notification_event", event_type=event_type)

    finally:
        await engine.dispose()

    log.info("send_notification_done", ticket_id=ticket_id, event_type=event_type)
