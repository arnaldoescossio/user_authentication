from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.dependencies import CurrentUser, get_token_cache, get_user_repository
from app.infrastructure.cache.token_cache import TokenCache
from app.infrastructure.database.user_repository import SQLUserRepository
from app.services.user_service import UserService

router = APIRouter(prefix="/account", tags=["Account"])


# ------------------------------------------------------------------ #
#  Schemas                                                             #
# ------------------------------------------------------------------ #


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def strength(cls, v: str) -> str:
        # Check bcrypt 72-byte limit
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes when encoded as UTF-8.")
        if not any(c.isupper() for c in v):
            raise ValueError("New password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("New password must contain at least one digit.")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def strength(cls, v: str) -> str:
        # Check bcrypt 72-byte limit
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes when encoded as UTF-8.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        return v


class VerifyEmailRequest(BaseModel):
    token: str


class MessageResponse(BaseModel):
    message: str


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #


def _get_user_service(
    repo: Annotated[SQLUserRepository, Depends(get_user_repository)],
    cache: Annotated[TokenCache, Depends(get_token_cache)],
) -> UserService:
    return UserService(user_repo=repo, token_cache=cache)


# ------------------------------------------------------------------ #
#  Routes                                                              #
# ------------------------------------------------------------------ #


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    body: ChangePasswordRequest,
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(_get_user_service)],
) -> MessageResponse:
    """Change the current user's password (requires knowing the current one)."""
    await user_service.change_password(
        user_id=current_user.id,
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return MessageResponse(message="Password changed successfully.")


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(
    body: ForgotPasswordRequest,
    user_service: Annotated[UserService, Depends(_get_user_service)],
) -> MessageResponse:
    """
    Request a password-reset token.
    Always returns 200 to prevent email enumeration — deliver the token via email.
    """
    token = await user_service.generate_password_reset_token(body.email)
    if token:
        # TODO: send token via email service, e.g. SendGrid / SES
        # email_service.send_reset(body.email, token)
        pass
    return MessageResponse(message="If that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    body: ResetPasswordRequest,
    user_service: Annotated[UserService, Depends(_get_user_service)],
) -> MessageResponse:
    """Confirm the reset token and set a new password."""
    await user_service.reset_password(token=body.token, new_password=body.new_password)
    return MessageResponse(message="Password has been reset. Please log in.")


@router.post("/send-verification", response_model=MessageResponse)
async def send_verification(
    current_user: CurrentUser,
    user_service: Annotated[UserService, Depends(_get_user_service)],
) -> MessageResponse:
    """Generate and (in a real system) email a verification token to the current user."""
    token = await user_service.generate_verification_token(current_user.id)
    # TODO: email_service.send_verification(current_user.email, token)
    return MessageResponse(message="Verification email sent.")


@router.post("/verify-email", response_model=MessageResponse)
async def verify_email(
    body: VerifyEmailRequest,
    user_service: Annotated[UserService, Depends(_get_user_service)],
) -> MessageResponse:
    """Confirm the email-verification token."""
    await user_service.confirm_email(body.token)
    return MessageResponse(message="Email verified successfully.")
