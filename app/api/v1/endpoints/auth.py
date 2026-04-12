from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.api.v1.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.dependencies import CurrentUser, get_auth_service
from app.core.exceptions import PasswordValidationException
from app.infrastructure.security.jwt import jwt_service
from app.services.audit_service import AuditLogService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    return (
        fwd.split(",")[0].strip()
        if fwd
        else (request.client.host if request.client else None)
    )


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    body: RegisterRequest,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    """Register a new user account."""
    try:
        user = await auth_service.register(
            email=body.email,
            username=body.username,
            password=body.password,
            full_name=body.full_name,
        )
    except ValueError as e:
        raise PasswordValidationException(detail=str(e))

    await AuditLogService.user_registered(user.id, ip=_ip(request))
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login_json(
    body: LoginRequest,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Login via JSON body — returns access + refresh tokens."""
    try:
        pair = await auth_service.login(email=body.email, password=body.password)
    except Exception:
        await AuditLogService.login_failed(body.email, ip=_ip(request))
        raise

    # Resolve user to get id for audit
    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.user_repository import SQLUserRepository

    async with AsyncSessionLocal() as s:
        user = await SQLUserRepository(s).get_by_email(body.email)
    if user:
        await AuditLogService.login_success(
            user.id,
            ip=_ip(request),
            ua=request.headers.get("user-agent"),
        )
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/login/form", response_model=TokenResponse, include_in_schema=True)
async def login_form(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """OAuth2 password-flow endpoint (username field = email). Used by Swagger UI."""
    try:
        pair = await auth_service.login(
            email=form_data.username,
            password=form_data.password,
        )
    except Exception:
        await AuditLogService.login_failed(form_data.username, ip=_ip(request))
        raise

    from app.infrastructure.database.session import AsyncSessionLocal
    from app.infrastructure.database.user_repository import SQLUserRepository

    async with AsyncSessionLocal() as s:
        user = await SQLUserRepository(s).get_by_email(form_data.username)
    if user:
        await AuditLogService.login_success(
            user.id,
            ip=_ip(request),
            ua=request.headers.get("user-agent"),
        )
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    """Issue a new token pair. The old refresh token is rotated immediately."""
    pair = await auth_service.refresh(refresh_token=body.refresh_token)
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token
    )


@router.post("/logout", status_code=204)
async def logout(
    body: LogoutRequest,
    current_user: CurrentUser,
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Revoke the current access token and optionally the refresh token."""
    raw_token: str = request.headers["authorization"].split(" ")[1]
    payload = jwt_service.decode_access_token(raw_token)
    await auth_service.logout(
        access_jti=payload["jti"],
        refresh_token=body.refresh_token,
    )
    await AuditLogService.logout(current_user.id, ip=_ip(request))


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(current_user)
