import uuid

import structlog

log = structlog.get_logger(__name__)


async def geocode_ticket(ctx: dict, ticket_id: str) -> None:
    """ARQ worker task: geocode a ticket's address and update lat/lon."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.core.enums import GeocodingStatus, TicketEventType  # noqa: PLC0415
    from app.models.ticket import Ticket  # noqa: PLC0415
    from app.services.geocoding import geocoding_service  # noqa: PLC0415
    from app.services.sse import broadcaster  # noqa: PLC0415

    log.info("geocode_ticket_start", ticket_id=ticket_id)

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Ticket).where(Ticket.id == uuid.UUID(ticket_id))
            )
            ticket = result.scalar_one_or_none()
            if ticket is None:
                log.warning("geocode_ticket_not_found", ticket_id=ticket_id)
                return

            if not ticket.address:
                log.info("geocode_no_address", ticket_id=ticket_id)
                ticket.geocoding_status = GeocodingStatus.FAILED
                db.add(ticket)
                await db.commit()
                return

            coords = await geocoding_service.geocode_address(ticket.address)
            if coords:
                lat, lon = coords
                ticket.lat = lat
                ticket.lon = lon
                ticket.geocoding_status = GeocodingStatus.DONE
            else:
                ticket.geocoding_status = GeocodingStatus.FAILED

            db.add(ticket)

            # Log event
            from app.core.enums import TicketEventType  # noqa: PLC0415, F811
            from app.models.ticket_event import TicketEvent  # noqa: PLC0415

            event = TicketEvent(
                ticket_id=ticket.id,
                actor_id=None,
                type=str(TicketEventType.GEOCODED),
                payload={
                    "status": str(ticket.geocoding_status),
                    "lat": ticket.lat,
                    "lon": ticket.lon,
                },
            )
            db.add(event)
            await db.commit()

            # Broadcast SSE
            try:
                await broadcaster.broadcast_to_role(
                    role="admin",
                    event_type="ticket.geocoded",
                    data={
                        "ticket_id": ticket_id,
                        "lat": ticket.lat,
                        "lon": ticket.lon,
                        "status": str(ticket.geocoding_status),
                    },
                )
            except Exception:
                pass

    finally:
        await engine.dispose()

    log.info("geocode_ticket_done", ticket_id=ticket_id, status=str(ticket.geocoding_status) if ticket else "unknown")
