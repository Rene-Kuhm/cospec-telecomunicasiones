import uuid
from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import UserRole
from app.models.email_verification_token import EmailVerificationToken
from app.models.password_reset_token import PasswordResetToken
from app.models.user import RefreshToken, User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(and_(User.email == email, User.deleted_at.is_(None)))
        )
        return result.scalar_one_or_none()

    async def get_techs(
        self,
        page: int = 1,
        limit: int = 20,
        zone: str | None = None,
        active: bool | None = None,
        skill: str | None = None,
    ) -> tuple[list[User], int]:
        from sqlalchemy import func  # noqa: PLC0415

        query = select(User).where(
            and_(User.role == UserRole.TECH, User.deleted_at.is_(None))
        )
        count_query = select(func.count()).select_from(User).where(
            and_(User.role == UserRole.TECH, User.deleted_at.is_(None))
        )

        if zone is not None:
            query = query.where(User.zone == zone)
            count_query = count_query.where(User.zone == zone)
        if active is not None:
            query = query.where(User.active == active)
            count_query = count_query.where(User.active == active)
        if skill is not None:
            query = query.where(User.skills.contains([skill]))
            count_query = count_query.where(User.skills.contains([skill]))

        total_result = await self.session.execute(count_query)
        total = total_result.scalar_one()

        query = query.offset((page - 1) * limit).limit(limit)
        result = await self.session.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def create_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def get_refresh_token(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at.is_(None),
                    RefreshToken.expires_at > datetime.now(UTC),
                )
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_hash: str) -> None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        token = result.scalar_one_or_none()
        if token:
            token.revoked_at = datetime.now(UTC)
            self.session.add(token)
            await self.session.flush()

    async def revoke_all_refresh_tokens(self, user_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(RefreshToken).where(
                and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        )
        tokens = result.scalars().all()
        now = datetime.now(UTC)
        for token in tokens:
            token.revoked_at = now
            self.session.add(token)
        await self.session.flush()

    async def create_email_verification_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> EmailVerificationToken:
        token = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def consume_email_verification_token(self, token_hash: str) -> User | None:
        result = await self.session.execute(
            select(EmailVerificationToken).where(
                and_(
                    EmailVerificationToken.token_hash == token_hash,
                    EmailVerificationToken.used_at.is_(None),
                    EmailVerificationToken.expires_at > datetime.now(UTC),
                )
            )
        )
        token = result.scalar_one_or_none()
        if token is None:
            return None

        token.used_at = datetime.now(UTC)
        self.session.add(token)

        user_result = await self.session.execute(
            select(User).where(User.id == token.user_id)
        )
        user = user_result.scalar_one_or_none()
        if user:
            user.email_verified = True
            user.email_verified_at = datetime.now(UTC)
            self.session.add(user)
        await self.session.flush()
        return user

    async def create_password_reset_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> PasswordResetToken:
        token = PasswordResetToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def consume_password_reset_token(self, token_hash: str) -> User | None:
        result = await self.session.execute(
            select(PasswordResetToken).where(
                and_(
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.used_at.is_(None),
                    PasswordResetToken.expires_at > datetime.now(UTC),
                )
            )
        )
        token = result.scalar_one_or_none()
        if token is None:
            return None

        token.used_at = datetime.now(UTC)
        self.session.add(token)

        user_result = await self.session.execute(
            select(User).where(User.id == token.user_id)
        )
        user = user_result.scalar_one_or_none()
        await self.session.flush()
        return user
