import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TicketPriority
from app.core.exceptions import ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_admin
from app.models.category import Category
from app.models.sla_rule import SLARule
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.common import ApiResponse, PaginatedResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    default_checklist: list[Any]
    required_skills: list[str]
    active: bool


class CategoryCreateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str
    slug: str
    default_checklist: list[Any] = []
    required_skills: list[str] = []


class CategoryPatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = None
    default_checklist: list[Any] | None = None
    required_skills: list[str] | None = None
    active: bool | None = None


class SLARuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    priority: TicketPriority
    sla_hours: int


class SLAConfigRequest(BaseModel):
    rules: list[dict[str, Any]]


@router.get("/categories", response_model=ApiResponse[PaginatedResponse[CategoryOut]])
async def list_categories(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[PaginatedResponse[CategoryOut]]:
    count_result = await db.execute(select(func.count()).select_from(Category))
    total = count_result.scalar_one()

    result = await db.execute(
        select(Category).order_by(Category.name).offset((page - 1) * limit).limit(limit)
    )
    items = list(result.scalars().all())
    out = [CategoryOut.model_validate(c) for c in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.post("/categories", response_model=ApiResponse[CategoryOut])
async def create_category(
    body: CategoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[CategoryOut]:
    # Check slug uniqueness
    existing = await db.execute(select(Category).where(Category.slug == body.slug))
    if existing.scalar_one_or_none():
        raise ConflictError(code="SLUG_ALREADY_EXISTS", message=f"Category slug '{body.slug}' already exists")

    category = Category(
        name=body.name,
        slug=body.slug,
        default_checklist=body.default_checklist,
        required_skills=body.required_skills,
    )
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return ApiResponse.ok(CategoryOut.model_validate(category))


@router.patch("/categories/{category_id}", response_model=ApiResponse[CategoryOut])
async def update_category(
    category_id: uuid.UUID,
    body: CategoryPatchRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[CategoryOut]:
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError(code="CATEGORY_NOT_FOUND", message=f"Category '{category_id}' not found")

    update_data = body.model_dump(exclude_none=True)
    for key, value in update_data.items():
        setattr(category, key, value)
    db.add(category)
    await db.flush()
    await db.refresh(category)
    return ApiResponse.ok(CategoryOut.model_validate(category))


@router.delete("/categories/{category_id}", response_model=ApiResponse[dict])
async def deactivate_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[dict]:
    result = await db.execute(select(Category).where(Category.id == category_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError(code="CATEGORY_NOT_FOUND", message=f"Category '{category_id}' not found")

    # Check for active tickets in this category
    active_count_result = await db.execute(
        select(func.count()).select_from(Ticket).where(
            and_(
                Ticket.category == category.slug,
                Ticket.status.notin_(["resuelto", "cerrado"]),
                Ticket.deleted_at.is_(None),
            )
        )
    )
    active_count = active_count_result.scalar_one()
    if active_count > 0:
        raise ConflictError(
            code="CATEGORY_HAS_ACTIVE_TICKETS",
            message=f"Cannot deactivate category with {active_count} active tickets",
        )

    category.active = False
    db.add(category)
    await db.flush()
    return ApiResponse.ok({"message": "Category deactivated"})


@router.get("/sla-config", response_model=ApiResponse[list[SLARuleOut]])
async def get_sla_config(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[list[SLARuleOut]]:
    result = await db.execute(
        select(SLARule).order_by(SLARule.category_id, SLARule.priority)
    )
    items = list(result.scalars().all())
    out = [SLARuleOut.model_validate(r) for r in items]
    return ApiResponse.ok(out)


@router.put("/sla-config", response_model=ApiResponse[list[SLARuleOut]])
async def update_sla_config(
    body: SLAConfigRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[list[SLARuleOut]]:
    updated_rules: list[SLARule] = []
    for rule_data in body.rules:
        category_id = uuid.UUID(str(rule_data["category_id"]))
        priority = rule_data["priority"]
        sla_hours = int(rule_data["sla_hours"])

        # Upsert SLA rule
        result = await db.execute(
            select(SLARule).where(
                and_(SLARule.category_id == category_id, SLARule.priority == priority)
            )
        )
        existing_rule = result.scalar_one_or_none()
        if existing_rule:
            existing_rule.sla_hours = sla_hours
            db.add(existing_rule)
            await db.flush()
            await db.refresh(existing_rule)
            updated_rules.append(existing_rule)
        else:
            new_rule = SLARule(
                category_id=category_id,
                priority=priority,
                sla_hours=sla_hours,
            )
            db.add(new_rule)
            await db.flush()
            await db.refresh(new_rule)
            updated_rules.append(new_rule)

    out = [SLARuleOut.model_validate(r) for r in updated_rules]
    return ApiResponse.ok(out)
