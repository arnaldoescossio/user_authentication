"""
Extended tests: UserService, password/verification flows, rate limiting logic.
Run with: pytest tests/ -v --asyncio-mode=auto
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import CredentialsException, UserNotFoundException
from app.domain.entities.user import User, UserRole, UserStatus
from app.infrastructure.security.password import hash_password
from app.services.user_service import UserService


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def make_user(**overrides) -> User:
    defaults = dict(
        email="bob@example.com",
        username="bob",
        hashed_password=hash_password("Secret123"),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
        is_verified=False,
    )
    return User(**(defaults | overrides))


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_cache() -> AsyncMock:
    cache = AsyncMock()
    cache._client = AsyncMock()
    return cache


@pytest.fixture
def user_service(mock_repo, mock_cache) -> UserService:
    return UserService(user_repo=mock_repo, token_cache=mock_cache)


# ------------------------------------------------------------------ #
#  UserService — profile                                               #
# ------------------------------------------------------------------ #

class TestUpdateProfile:
    @pytest.mark.asyncio
    async def test_update_full_name(self, user_service, mock_repo):
        user = make_user()
        mock_repo.get_by_id.return_value = user
        mock_repo.update.return_value = user.model_copy(update={"full_name": "Bob Smith"})

        result = await user_service.update_profile(user_id=user.id, full_name="Bob Smith")
        assert result.full_name == "Bob Smith"
        mock_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_changes_returns_user(self, user_service, mock_repo):
        user = make_user()
        mock_repo.get_by_id.return_value = user

        result = await user_service.update_profile(user_id=user.id)
        assert result == user
        mock_repo.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self, user_service, mock_repo):
        mock_repo.get_by_id.return_value = None
        with pytest.raises(UserNotFoundException):
            await user_service.update_profile(user_id=uuid.uuid4(), full_name="X")


# ------------------------------------------------------------------ #
#  UserService — password change                                       #
# ------------------------------------------------------------------ #

class TestChangePassword:
    @pytest.mark.asyncio
    async def test_correct_current_password_succeeds(self, user_service, mock_repo):
        user = make_user()
        mock_repo.get_by_id.return_value = user
        mock_repo.update.return_value = user

        await user_service.change_password(
            user_id=user.id,
            current_password="Secret123",
            new_password="NewPass456",
        )
        mock_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrong_current_password_raises(self, user_service, mock_repo):
        user = make_user()
        mock_repo.get_by_id.return_value = user

        with pytest.raises(CredentialsException):
            await user_service.change_password(
                user_id=user.id,
                current_password="WrongPass",
                new_password="NewPass456",
            )


# ------------------------------------------------------------------ #
#  UserService — email verification                                    #
# ------------------------------------------------------------------ #

class TestEmailVerification:
    @pytest.mark.asyncio
    async def test_generate_token_stores_in_redis(self, user_service, mock_cache):
        user_id = uuid.uuid4()
        mock_cache._client.setex = AsyncMock()

        token = await user_service.generate_verification_token(user_id)
        assert len(token) > 20
        mock_cache._client.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_confirm_email_marks_verified(self, user_service, mock_repo, mock_cache):
        user = make_user()
        mock_cache._client.get.return_value = str(user.id).encode()
        mock_cache._client.delete = AsyncMock()
        mock_repo.get_by_id.return_value = user
        mock_repo.update.return_value = user.model_copy(update={"is_verified": True})

        result = await user_service.confirm_email("some-token")
        assert result.is_verified is True

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self, user_service, mock_cache):
        mock_cache._client.get.return_value = None

        with pytest.raises(CredentialsException):
            await user_service.confirm_email("bad-token")


# ------------------------------------------------------------------ #
#  UserService — password reset                                        #
# ------------------------------------------------------------------ #

class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_unknown_email_returns_none(self, user_service, mock_repo):
        mock_repo.get_by_email.return_value = None
        token = await user_service.generate_password_reset_token("ghost@example.com")
        assert token is None

    @pytest.mark.asyncio
    async def test_known_email_returns_token(self, user_service, mock_repo, mock_cache):
        user = make_user()
        mock_repo.get_by_email.return_value = user
        mock_cache._client.setex = AsyncMock()

        token = await user_service.generate_password_reset_token(user.email)
        assert token is not None and len(token) > 20

    @pytest.mark.asyncio
    async def test_reset_with_valid_token(self, user_service, mock_repo, mock_cache):
        user = make_user()
        mock_cache._client.get.return_value = str(user.id).encode()
        mock_cache._client.delete = AsyncMock()
        mock_repo.get_by_id.return_value = user
        mock_repo.update.return_value = user

        await user_service.reset_password(token="valid-token", new_password="NewPass789")
        mock_repo.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reset_with_invalid_token_raises(self, user_service, mock_cache):
        mock_cache._client.get.return_value = None

        with pytest.raises(CredentialsException):
            await user_service.reset_password(token="bad-token", new_password="NewPass789")


# ------------------------------------------------------------------ #
#  UserService — admin status/role management                          #
# ------------------------------------------------------------------ #

class TestAdminManagement:
    @pytest.mark.asyncio
    async def test_set_status_banned(self, user_service, mock_repo):
        user = make_user()
        mock_repo.get_by_id.return_value = user
        mock_repo.update.return_value = user.model_copy(update={"status": UserStatus.BANNED})

        result = await user_service.set_status(user_id=user.id, status=UserStatus.BANNED)
        assert result.status == UserStatus.BANNED

    @pytest.mark.asyncio
    async def test_set_role_to_moderator(self, user_service, mock_repo):
        user = make_user()
        mock_repo.get_by_id.return_value = user
        mock_repo.update.return_value = user.model_copy(update={"role": UserRole.MODERATOR})

        result = await user_service.set_role(user_id=user.id, role=UserRole.MODERATOR)
        assert result.role == UserRole.MODERATOR
