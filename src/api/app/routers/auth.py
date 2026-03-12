import structlog
from fastapi import APIRouter, Cookie, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    AuthData,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.schemas.common import ApiResponse
from app.schemas.user import UserOut
from app.services.auth import AuthService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE_NAME = "refresh_token"
COOKIE_PATH = "/api/v1/auth/refresh"


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.APP_ENV != "development",
        samesite="strict",
        path=COOKIE_PATH,
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=COOKIE_PATH)


@router.post("/register", response_model=ApiResponse[AuthData])
async def register(
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AuthData]:
    repo = UserRepository(db)
    service = AuthService(repo)
    user, access_token, refresh_token = await service.register(body)
    _set_refresh_cookie(response, refresh_token)
    return ApiResponse.ok(
        AuthData(access_token=access_token, user=UserOut.model_validate(user))
    )


@router.post("/login", response_model=ApiResponse[AuthData])
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AuthData]:
    repo = UserRepository(db)
    service = AuthService(repo)
    user, access_token, refresh_token = await service.login(body.email, body.password)
    _set_refresh_cookie(response, refresh_token)
    return ApiResponse.ok(
        AuthData(access_token=access_token, user=UserOut.model_validate(user))
    )


@router.post("/refresh", response_model=ApiResponse[RefreshResponse])
async def refresh(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> ApiResponse[RefreshResponse]:
    """Rotate refresh token. Reads refresh_token from HttpOnly cookie."""
    from app.core.exceptions import AuthError  # noqa: PLC0415

    if refresh_token is None:
        raise AuthError(code="MISSING_REFRESH_TOKEN", message="Refresh token cookie required")

    repo = UserRepository(db)
    service = AuthService(repo)
    new_access, new_refresh = await service.refresh(refresh_token)
    _set_refresh_cookie(response, new_refresh)
    return ApiResponse.ok(RefreshResponse(access_token=new_access))


@router.post("/logout", response_model=ApiResponse[dict])
async def logout(
    response: Response,
    db: AsyncSession = Depends(get_db),
    refresh_token: str | None = Cookie(default=None, alias="refresh_token"),
) -> ApiResponse[dict]:
    if refresh_token:
        repo = UserRepository(db)
        service = AuthService(repo)
        await service.logout(refresh_token)
    _clear_refresh_cookie(response)
    return ApiResponse.ok({"message": "Logged out successfully"})


@router.get("/me", response_model=ApiResponse[UserOut])
async def get_me(
    current_user: User = Depends(get_current_user),
) -> ApiResponse[UserOut]:
    return ApiResponse.ok(UserOut.model_validate(current_user))


@router.post("/verify-email", response_model=ApiResponse[UserOut])
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UserOut]:
    repo = UserRepository(db)
    service = AuthService(repo)
    user = await service.verify_email(body.token)
    return ApiResponse.ok(UserOut.model_validate(user))


@router.post("/forgot-password", response_model=ApiResponse[dict])
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    repo = UserRepository(db)
    service = AuthService(repo)
    await service.forgot_password(body.email)
    return ApiResponse.ok({"message": "If that email exists, a reset link has been sent"})


@router.post("/reset-password", response_model=ApiResponse[dict])
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[dict]:
    repo = UserRepository(db)
    service = AuthService(repo)
    await service.reset_password(body.token, body.new_password)
    return ApiResponse.ok({"message": "Password reset successfully"})
