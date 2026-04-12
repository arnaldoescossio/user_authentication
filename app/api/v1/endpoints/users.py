from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.v1.schemas import AdminUserUpdateRequest, UserResponse, UserUpdateRequest
from app.core.dependencies import AdminUser, CurrentUser, get_user_repository
from app.core.exceptions import UserNotFoundException
from app.infrastructure.database.user_repository import SQLUserRepository

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me", response_model=UserResponse)
async def get_my_profile(current_user: CurrentUser) -> UserResponse:
    """Return the current user's full profile."""
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    body: UserUpdateRequest,
    current_user: CurrentUser,
    repo: Annotated[SQLUserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """Update the current user's own profile fields."""
    updated = current_user.model_copy(
        update={k: v for k, v in body.model_dump().items() if v is not None}
    )
    saved = await repo.update(updated)
    return UserResponse.model_validate(saved)


# ------------------------------------------------------------------ #
#  Admin-only endpoints                                                #
# ------------------------------------------------------------------ #

@router.get("/{user_id}", response_model=UserResponse, dependencies=[])
async def get_user_by_id(
    user_id: uuid.UUID,
    _admin: AdminUser,
    repo: Annotated[SQLUserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """[Admin] Retrieve any user by ID."""
    user = await repo.get_by_id(user_id)
    if not user:
        raise UserNotFoundException(str(user_id))
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def admin_update_user(
    user_id: uuid.UUID,
    body: AdminUserUpdateRequest,
    _admin: AdminUser,
    repo: Annotated[SQLUserRepository, Depends(get_user_repository)],
) -> UserResponse:
    """[Admin] Update any user's profile, role, or status."""
    user = await repo.get_by_id(user_id)
    if not user:
        raise UserNotFoundException(str(user_id))

    updated = user.model_copy(
        update={k: v for k, v in body.model_dump().items() if v is not None}
    )
    saved = await repo.update(updated)
    return UserResponse.model_validate(saved)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    _admin: AdminUser,
    repo: Annotated[SQLUserRepository, Depends(get_user_repository)],
) -> None:
    """[Admin] Permanently delete a user."""
    user = await repo.get_by_id(user_id)
    if not user:
        raise UserNotFoundException(str(user_id))
    await repo.delete(user_id)
