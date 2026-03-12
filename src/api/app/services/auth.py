import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog

from app.config import settings
from app.core.enums import UserRole
from app.core.exceptions import AuthError, ConflictError, ValidationError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import RegisterRequest

log = structlog.get_logger(__name__)


class AuthService:
    def __init__(self, user_repo: UserRepository) -> None:
        self.user_repo = user_repo

    async def register(self, data: RegisterRequest) -> tuple[User, str, str]:
        existing = await self.user_repo.get_by_email(data.email)
        if existing is not None:
            raise ConflictError(
                code="EMAIL_ALREADY_EXISTS",
                message="A user with this email already exists",
            )

        user = await self.user_repo.create(
            role=UserRole.CUSTOMER,
            name=data.name,
            email=data.email.lower(),
            phone=data.phone,
            password_hash=hash_password(data.password),
            skills=[],
        )

        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            email=user.email,
        )
        refresh_token_plain = create_refresh_token()
        refresh_token_hash = hash_token(refresh_token_plain)
        expires_at = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        await self.user_repo.create_refresh_token(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=expires_at,
        )

        # Queue verification email (fire-and-forget)
        await self._queue_verification_email(user)

        log.info("user_registered", user_id=str(user.id), email=user.email)
        return user, access_token, refresh_token_plain

    async def login(self, email: str, password: str) -> tuple[User, str, str]:
        user = await self.user_repo.get_by_email(email.lower())
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError(
                code="INVALID_CREDENTIALS",
                message="Invalid email or password",
            )

        if not user.active:
            raise AuthError(code="USER_INACTIVE", message="User account is disabled")

        access_token = create_access_token(
            user_id=str(user.id),
            role=user.role,
            email=user.email,
        )
        refresh_token_plain = create_refresh_token()
        refresh_token_hash = hash_token(refresh_token_plain)
        expires_at = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        await self.user_repo.create_refresh_token(
            user_id=user.id,
            token_hash=refresh_token_hash,
            expires_at=expires_at,
        )

        log.info("user_logged_in", user_id=str(user.id))
        return user, access_token, refresh_token_plain

    async def refresh(self, refresh_token: str) -> tuple[str, str]:
        token_hash = hash_token(refresh_token)
        db_token = await self.user_repo.get_refresh_token(token_hash)
        if db_token is None:
            raise AuthError(code="INVALID_REFRESH_TOKEN", message="Invalid or expired refresh token")

        # Revoke old token (rotation)
        await self.user_repo.revoke_refresh_token(token_hash)

        user_result = await self.user_repo.get_by_id(db_token.user_id)
        if user_result is None or not user_result.active:
            raise AuthError(code="USER_NOT_FOUND", message="User not found or inactive")

        new_access = create_access_token(
            user_id=str(user_result.id),
            role=user_result.role,
            email=user_result.email,
        )
        new_refresh_plain = create_refresh_token()
        new_refresh_hash = hash_token(new_refresh_plain)
        expires_at = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        await self.user_repo.create_refresh_token(
            user_id=user_result.id,
            token_hash=new_refresh_hash,
            expires_at=expires_at,
        )

        return new_access, new_refresh_plain

    async def logout(self, refresh_token: str) -> None:
        token_hash = hash_token(refresh_token)
        await self.user_repo.revoke_refresh_token(token_hash)
        log.info("user_logged_out")

    async def verify_email(self, token: str) -> User:
        token_hash = hash_token(token)
        user = await self.user_repo.consume_email_verification_token(token_hash)
        if user is None:
            raise ValidationError(
                code="INVALID_VERIFICATION_TOKEN",
                message="Invalid or expired verification token",
            )
        log.info("email_verified", user_id=str(user.id))
        return user

    async def forgot_password(self, email: str) -> None:
        user = await self.user_repo.get_by_email(email.lower())
        # Never reveal whether email exists
        if user is None:
            log.info("forgot_password_email_not_found", email=email)
            return

        token_plain = secrets.token_urlsafe(32)
        token_hash = hash_token(token_plain)
        expires_at = datetime.now(UTC) + timedelta(hours=1)
        await self.user_repo.create_password_reset_token(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        await self._queue_password_reset_email(user, token_plain)
        log.info("password_reset_requested", user_id=str(user.id))

    async def reset_password(self, token: str, new_password: str) -> None:
        token_hash = hash_token(token)
        user = await self.user_repo.consume_password_reset_token(token_hash)
        if user is None:
            raise ValidationError(
                code="INVALID_RESET_TOKEN",
                message="Invalid or expired password reset token",
            )

        user.password_hash = hash_password(new_password)
        # Revoke all existing refresh tokens for security
        await self.user_repo.revoke_all_refresh_tokens(user.id)
        log.info("password_reset", user_id=str(user.id))

    async def _queue_verification_email(self, user: User) -> None:
        """Queue email verification in ARQ — fire and forget."""
        try:
            from app.workers.notifications import send_notification  # noqa: PLC0415

            token_plain = secrets.token_urlsafe(32)
            token_hash = hash_token(token_plain)
            expires_at = datetime.now(UTC) + timedelta(hours=24)
            await self.user_repo.create_email_verification_token(
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        except Exception:
            log.warning("failed_to_queue_verification_email", user_id=str(user.id))

    async def _queue_password_reset_email(self, user: User, token: str) -> None:
        """Queue password reset email in ARQ — fire and forget."""
        log.info("queue_password_reset_email", user_id=str(user.id))
