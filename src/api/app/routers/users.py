import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.database import get_db
from app.dependencies import get_admin, get_any_role, get_current_user
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.user import (
    CustomerCreateRequest,
    TechCreateRequest,
    TechUpdateRequest,
    UserOut,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.post("/tech", response_model=ApiResponse[UserOut])
async def create_tech(
    body: TechCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[UserOut]:
    repo = UserRepository(db)
    user = await repo.create(
        role=UserRole.TECH,
        name=body.name,
        email=body.email.lower(),
        phone=body.phone,
        password_hash=hash_password(body.password),
        zone=body.zone,
        skills=body.skills,
        email_verified=True,
    )
    return ApiResponse.ok(UserOut.model_validate(user))


@router.get("/tech", response_model=ApiResponse[PaginatedResponse[UserOut]])
async def list_techs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    zone: str | None = Query(None),
    active: bool | None = Query(None),
    skill: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_any_role),
) -> ApiResponse[PaginatedResponse[UserOut]]:
    repo = UserRepository(db)
    items, total = await repo.get_techs(page=page, limit=limit, zone=zone, active=active, skill=skill)
    out = [UserOut.model_validate(u) for u in items]
    return ApiResponse.ok(PaginatedResponse.of(items=out, total=total, page=page, limit=limit))


@router.get("/tech/{tech_id}", response_model=ApiResponse[UserOut])
async def get_tech(
    tech_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_any_role),
) -> ApiResponse[UserOut]:
    repo = UserRepository(db)
    tech = await repo.get_by_id(tech_id)
    if tech is None or tech.role != UserRole.TECH:
        raise NotFoundError(code="TECH_NOT_FOUND", message=f"Technician '{tech_id}' not found")
    return ApiResponse.ok(UserOut.model_validate(tech))


@router.patch("/tech/{tech_id}", response_model=ApiResponse[UserOut])
async def update_tech(
    tech_id: uuid.UUID,
    body: TechUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[UserOut]:
    repo = UserRepository(db)
    tech = await repo.get_by_id(tech_id)
    if tech is None or tech.role != UserRole.TECH:
        raise NotFoundError(code="TECH_NOT_FOUND", message=f"Technician '{tech_id}' not found")

    update_data = body.model_dump(exclude_none=True)
    updated = await repo.update(tech, **update_data)
    return ApiResponse.ok(UserOut.model_validate(updated))


@router.post("/customer", response_model=ApiResponse[UserOut])
async def create_customer(
    body: CustomerCreateRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin),
) -> ApiResponse[UserOut]:
    repo = UserRepository(db)
    user = await repo.create(
        role=UserRole.CUSTOMER,
        name=body.name,
        email=body.email.lower(),
        phone=body.phone,
        password_hash=hash_password(body.password),
        skills=[],
    )
    return ApiResponse.ok(UserOut.model_validate(user))


@router.post("/{user_id}/resend-verification", response_model=ApiResponse[dict])
async def resend_verification(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[dict]:
    from app.core.exceptions import ForbiddenError  # noqa: PLC0415

    # Admin can resend for anyone; customers only for themselves
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise ForbiddenError(
            code="FORBIDDEN",
            message="You can only resend verification for your own account",
        )

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundError(code="USER_NOT_FOUND", message=f"User '{user_id}' not found")

    # Re-use auth service to queue new verification token
    from app.services.auth import AuthService  # noqa: PLC0415

    service = AuthService(repo)
    await service._queue_verification_email(user)

    return ApiResponse.ok({"message": "Verification email resent"})
