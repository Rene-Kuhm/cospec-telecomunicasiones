from collections.abc import AsyncGenerator
from typing import Annotated

import structlog
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.user import User
from app.repositories.user import UserRepository

log = structlog.get_logger(__name__)


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization:
        raise AuthError(code="MISSING_TOKEN", message="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise AuthError(code="INVALID_TOKEN_FORMAT", message="Token must be Bearer type")

    token = authorization.removeprefix("Bearer ")
    payload = decode_access_token(token)

    user_id = payload.get("sub")
    if not user_id:
        raise AuthError(code="INVALID_TOKEN", message="Token missing subject claim")

    import uuid  # noqa: PLC0415

    repo = UserRepository(db)
    user = await repo.get_by_id(uuid.UUID(user_id))
    if user is None or user.deleted_at is not None:
        raise AuthError(code="USER_NOT_FOUND", message="User not found")

    if not user.active:
        raise AuthError(code="USER_INACTIVE", message="User account is disabled")

    return user


def require_role(*roles: UserRole):
    async def checker(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role not in roles:
            raise ForbiddenError(
                code="INSUFFICIENT_ROLE",
                message=f"Role '{current_user.role}' is not authorized for this action",
            )
        return current_user

    return checker


# Shorthand dependency callables
get_admin = require_role(UserRole.ADMIN)
get_tech = require_role(UserRole.TECH)
get_customer = require_role(UserRole.CUSTOMER)
get_admin_or_tech = require_role(UserRole.ADMIN, UserRole.TECH)
get_any_role = require_role(UserRole.ADMIN, UserRole.TECH, UserRole.CUSTOMER)
