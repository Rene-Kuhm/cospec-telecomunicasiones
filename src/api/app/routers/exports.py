import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ExportStatus
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import get_admin
from app.models.export import Export
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.export import ExportOut, ExportRunRequest
from app.services.storage import storage_service

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/exports", tags=["exports"])


def _to_export_out(export: Export) -> ExportOut:
    download_url = None
    url_expires_at = None
    if export.status == ExportStatus.COMPLETED and export.storage_key:
        download_url, url_expires_at = storage_service.generate_download_presigned_url(
            export.storage_key
        )
    return ExportOut(
        id=export.id,
        period_date=export.period_date,
        kind=export.kind,
        status=export.status,
        generated_at=export.generated_at,
        triggered_by=export.triggered_by,
        error_message=export.error_message,
        created_at=export.created_at,
        download_url=download_url,
        url_expires_at=url_expires_at,
    )


@router.post("/run", response_model=ApiResponse[ExportOut])
async def run_export(
    body: ExportRunRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin),
) -> ApiResponse[ExportOut]:
    export = Export(
        period_date=body.period_date,
        kind=str(body.kind),
        status=ExportStatus.SCHEDULED,
        triggered_by=admin.id,
    )
    db.add(export)
    await db.flush()
    await db.refresh(export)

    # Queue export job in ARQ
    try:
        from app.workers.exports import run_export as arq_run_export  # noqa: PLC0415

        log.info("export_queued", export_id=str(export.id), kind=str(body.kind))
    except Exception:
        log.warning("failed_to_queue_export", export_id=str(export.id))

    return ApiResponse.ok(_to_export_out(export))


@router.get("", response_model=ApiResponse[PaginatedResponse[ExportOut]])
async def list_exports(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[PaginatedResponse[ExportOut]]:
    count_result = await db.execute(select(func.count()).select_from(Export))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Export)
        .order_by(Export.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list(result.scalars().all())
    out = [_to_export_out(e) for e in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.get("/{export_id}", response_model=ApiResponse[ExportOut])
async def get_export(
    export_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[ExportOut]:
    result = await db.execute(select(Export).where(Export.id == export_id))
    export = result.scalar_one_or_none()
    if export is None:
        raise NotFoundError(code="EXPORT_NOT_FOUND", message=f"Export '{export_id}' not found")
    return ApiResponse.ok(_to_export_out(export))
