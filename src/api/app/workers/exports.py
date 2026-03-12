import uuid
from datetime import UTC, datetime, timedelta

import structlog

log = structlog.get_logger(__name__)


async def run_export(ctx: dict, export_id: str) -> None:
    """ARQ worker task: generate an XLSX export and upload to storage."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415
    from sqlalchemy import select, and_  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.core.enums import ExportStatus, TicketStatus  # noqa: PLC0415
    from app.models.export import Export  # noqa: PLC0415
    from app.models.ticket import Ticket  # noqa: PLC0415
    from app.models.user import User  # noqa: PLC0415
    from app.services.storage import storage_service  # noqa: PLC0415

    log.info("run_export_start", export_id=export_id)

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Export).where(Export.id == uuid.UUID(export_id))
            )
            export = result.scalar_one_or_none()
            if export is None:
                log.error("export_not_found", export_id=export_id)
                return

            export.status = ExportStatus.RUNNING
            db.add(export)
            await db.commit()

            try:
                # Determine date range based on kind
                period = export.period_date
                if export.kind == "daily":
                    date_from = period.replace(hour=0, minute=0, second=0, microsecond=0)
                    date_to = date_from + timedelta(days=1)
                elif export.kind == "monthly":
                    date_from = period.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    import calendar  # noqa: PLC0415
                    last_day = calendar.monthrange(period.year, period.month)[1]
                    date_to = date_from.replace(day=last_day) + timedelta(days=1)
                else:  # annual
                    date_from = period.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
                    date_to = date_from.replace(year=period.year + 1)

                # Fetch tickets in range
                tickets_result = await db.execute(
                    select(Ticket).where(
                        and_(
                            Ticket.created_at >= date_from,
                            Ticket.created_at < date_to,
                            Ticket.deleted_at.is_(None),
                        )
                    ).order_by(Ticket.created_at).limit(settings.EXPORT_MAX_ROWS)
                )
                tickets = list(tickets_result.scalars().all())

                # Generate XLSX
                import io  # noqa: PLC0415
                import openpyxl  # noqa: PLC0415

                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = f"{export.kind} - {period.strftime('%Y-%m-%d')}"

                headers = [
                    "ID", "Title", "Category", "Priority", "Status",
                    "Customer ID", "Assigned To", "Address",
                    "SLA Due At", "Created At", "Closed At",
                ]
                ws.append(headers)

                for ticket in tickets:
                    ws.append([
                        str(ticket.id),
                        ticket.title,
                        ticket.category,
                        ticket.priority,
                        ticket.status,
                        str(ticket.customer_id),
                        str(ticket.assigned_to) if ticket.assigned_to else "",
                        ticket.address or "",
                        ticket.sla_due_at.isoformat() if ticket.sla_due_at else "",
                        ticket.created_at.isoformat(),
                        ticket.closed_at.isoformat() if ticket.closed_at else "",
                    ])

                buffer = io.BytesIO()
                wb.save(buffer)
                buffer.seek(0)

                # Upload to storage
                period_str = period.strftime("%Y-%m-%d")
                storage_key = storage_service.build_export_key(
                    export_id=export.id,
                    kind=export.kind,
                    period=period_str,
                )

                storage_service.client.put_object(
                    Bucket=settings.STORAGE_BUCKET_NAME,
                    Key=storage_key,
                    Body=buffer.getvalue(),
                    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                export.storage_key = storage_key
                export.status = ExportStatus.COMPLETED
                export.generated_at = datetime.now(UTC)

            except Exception as exc:
                log.error("export_generation_failed", export_id=export_id, error=str(exc))
                export.status = ExportStatus.FAILED
                export.error_message = str(exc)

            db.add(export)
            await db.commit()

            # Broadcast SSE to admins
            try:
                from app.services.sse import broadcaster  # noqa: PLC0415

                await broadcaster.broadcast_to_role(
                    role="admin",
                    event_type="export.done",
                    data={"export_id": export_id, "status": str(export.status)},
                )
            except Exception:
                pass

    finally:
        await engine.dispose()

    log.info("run_export_done", export_id=export_id)


async def daily_export(ctx: dict) -> None:
    """Cron job: trigger daily export for yesterday."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.core.enums import ExportKind  # noqa: PLC0415
    from app.models.export import Export  # noqa: PLC0415

    yesterday = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            export = Export(
                period_date=yesterday,
                kind=ExportKind.DAILY,
                status="scheduled",
            )
            db.add(export)
            await db.commit()
            await db.refresh(export)
            await ctx["redis"].enqueue_job("run_export", str(export.id))
    finally:
        await engine.dispose()

    log.info("daily_export_queued", period=str(yesterday.date()))


async def monthly_export(ctx: dict) -> None:
    """Cron job: trigger monthly export for last month."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.core.enums import ExportKind  # noqa: PLC0415
    from app.models.export import Export  # noqa: PLC0415

    today = datetime.now(UTC)
    first_of_last_month = today.replace(day=1) - timedelta(days=1)
    first_of_last_month = first_of_last_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            export = Export(
                period_date=first_of_last_month,
                kind=ExportKind.MONTHLY,
                status="scheduled",
            )
            db.add(export)
            await db.commit()
            await db.refresh(export)
            await ctx["redis"].enqueue_job("run_export", str(export.id))
    finally:
        await engine.dispose()

    log.info("monthly_export_queued", period=str(first_of_last_month.date()))


async def annual_export(ctx: dict) -> None:
    """Cron job: trigger annual export for last year."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.core.enums import ExportKind  # noqa: PLC0415
    from app.models.export import Export  # noqa: PLC0415

    last_year = datetime.now(UTC).replace(year=datetime.now(UTC).year - 1, month=1, day=1,
                                          hour=0, minute=0, second=0, microsecond=0)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            export = Export(
                period_date=last_year,
                kind=ExportKind.ANNUAL,
                status="scheduled",
            )
            db.add(export)
            await db.commit()
            await db.refresh(export)
            await ctx["redis"].enqueue_job("run_export", str(export.id))
    finally:
        await engine.dispose()

    log.info("annual_export_queued", period=str(last_year.year))


async def check_sla_breaches(ctx: dict) -> None:
    """Cron job: detect SLA breaches and broadcast SSE alerts."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: PLC0415
    from sqlalchemy import select, and_  # noqa: PLC0415

    from app.config import settings  # noqa: PLC0415
    from app.core.enums import TicketStatus  # noqa: PLC0415
    from app.models.ticket import Ticket  # noqa: PLC0415
    from app.services.sse import broadcaster  # noqa: PLC0415

    now = datetime.now(UTC)
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with SessionLocal() as db:
            result = await db.execute(
                select(Ticket).where(
                    and_(
                        Ticket.deleted_at.is_(None),
                        Ticket.sla_due_at.isnot(None),
                        Ticket.sla_due_at < now,
                        Ticket.status.notin_([TicketStatus.RESUELTO, TicketStatus.CERRADO]),
                    )
                ).limit(100)
            )
            breached_tickets = list(result.scalars().all())

        if breached_tickets:
            await broadcaster.broadcast_to_role(
                role="admin",
                event_type="ticket.sla_breach",
                data={
                    "count": len(breached_tickets),
                    "ticket_ids": [str(t.id) for t in breached_tickets],
                },
            )
            log.warning("sla_breaches_detected", count=len(breached_tickets))
        else:
            log.info("sla_check_no_breaches")

    finally:
        await engine.dispose()
