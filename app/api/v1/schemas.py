from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.domain.entities.user import UserRole, UserStatus

# ------------------------------------------------------------------ #
#  Auth schemas                                                        #
# ------------------------------------------------------------------ #


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=72)
    full_name: str | None = Field(default=None, max_length=120)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # Check bcrypt 72-byte limit
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 bytes when encoded as UTF-8.")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(not c.isalnum() for c in v):
            raise ValueError("Password must contain at least one special character.")
        return v


class LoginRequest(BaseModel):
    """Used for JSON-body login (separate from OAuth2 form login)."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


# ------------------------------------------------------------------ #
#  User schemas                                                        #
# ------------------------------------------------------------------ #


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str | None
    role: UserRole
    status: UserStatus
    is_verified: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, min_length=3, max_length=50)


class AdminUserUpdateRequest(UserUpdateRequest):
    role: UserRole | None = None
    status: UserStatus | None = None
    is_verified: bool | None = None
