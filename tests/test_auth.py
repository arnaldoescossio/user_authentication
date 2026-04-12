"""
Unit tests for: password hashing, JWTService, AuthService.
All infrastructure is mocked — no DB, no Redis.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import CredentialsException, TokenRevokedException, UserAlreadyExistsException
from app.domain.entities.user import User, UserRole, UserStatus
from app.infrastructure.security.jwt import JWTService
from app.infrastructure.security.password import hash_password, verify_password
from app.services.auth_service import AuthService


# ------------------------------------------------------------------ #
#  Helpers                                                             #
# ------------------------------------------------------------------ #

def make_user(**kw) -> User:
    return User(**(dict(
        email="alice@example.com",
        username="alice",
        hashed_password=hash_password("Secret123"),
        role=UserRole.USER,
        status=UserStatus.ACTIVE,
    ) | kw))


class FakeTokenRepo:
    """In-memory AbstractTokenRepository for unit tests."""
    def __init__(self):
        self._refresh: dict[str, str] = {}
        self._denied:  set[str]       = set()

    async def store_refresh(self, jti, user_id, ttl_seconds): self._refresh[jti] = user_id
    async def get_refresh_owner(self, jti): return self._refresh.get(jti)
    async def revoke_refresh(self, jti): self._refresh.pop(jti, None)
    async def revoke_all_refresh_for_user(self, user_id):
        for jti in [k for k, v in self._refresh.items() if v == user_id]:
            del self._refresh[jti]
    async def deny_access(self, jti, ttl_seconds): self._denied.add(jti)
    async def is_access_denied(self, jti): return jti in self._denied


@pytest.fixture
def token_repo() -> FakeTokenRepo:
    return FakeTokenRepo()


@pytest.fixture
def mock_user_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.exists_by_email.return_value = False
    return repo


@pytest.fixture
def auth_service(mock_user_repo, token_repo) -> AuthService:
    return AuthService(user_repo=mock_user_repo, token_repo=token_repo)


@pytest.fixture
def jwt() -> JWTService:
    return JWTService()


# ------------------------------------------------------------------ #
#  Password                                                            #
# ------------------------------------------------------------------ #

class TestPassword:
    def test_hash_and_verify(self):
        h = hash_password("MyPassword1")
        assert verify_password("MyPassword1", h)

    def test_wrong_password_fails(self):
        h = hash_password("MyPassword1")
        assert not verify_password("Wrong", h)

    def test_hashes_are_unique(self):
        assert hash_password("same") != hash_password("same")


# ------------------------------------------------------------------ #
#  JWT                                                                 #
# ------------------------------------------------------------------ #

class TestJWT:
    def test_access_roundtrip(self, jwt):
        uid = str(uuid.uuid4())
        token, jti = jwt.create_access_token(uid, "user")
        p = jwt.decode_access_token(token)
        assert p["sub"] == uid and p["jti"] == jti and p["type"] == "access"

    def test_refresh_roundtrip(self, jwt):
        uid = str(uuid.uuid4())
        token, jti = jwt.create_refresh_token(uid)
        p = jwt.decode_refresh_token(token)
        assert p["sub"] == uid and p["jti"] == jti and p["type"] == "refresh"

    def test_wrong_type_raises(self, jwt):
        token, _ = jwt.create_access_token("u1", "user")
        with pytest.raises(CredentialsException):
            jwt.decode_refresh_token(token)

    def test_tampered_token_raises(self, jwt):
        token, _ = jwt.create_access_token("u1", "user")
        with pytest.raises(CredentialsException):
            jwt.decode_access_token(token + "x")


# ------------------------------------------------------------------ #
#  AuthService                                                         #
# ------------------------------------------------------------------ #

class TestRegister:
    @pytest.mark.asyncio
    async def test_success(self, auth_service, mock_user_repo):
        user = make_user()
        mock_user_repo.create.return_value = user
        result = await auth_service.register(email="alice@example.com",
                                             username="alice", password="Secret123")
        assert result.email == "alice@example.com"
        mock_user_repo.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_duplicate_email_raises(self, auth_service, mock_user_repo):
        mock_user_repo.exists_by_email.return_value = True
        with pytest.raises(UserAlreadyExistsException):
            await auth_service.register(email="alice@example.com",
                                        username="alice", password="Secret123")


class TestLogin:
    @pytest.mark.asyncio
    async def test_success_returns_tokens(self, auth_service, mock_user_repo, token_repo):
        user = make_user()
        mock_user_repo.get_by_email.return_value = user
        pair = await auth_service.login(email="alice@example.com", password="Secret123")
        assert pair.access_token and pair.refresh_token

    @pytest.mark.asyncio
    async def test_wrong_password_raises(self, auth_service, mock_user_repo):
        mock_user_repo.get_by_email.return_value = make_user()
        with pytest.raises(CredentialsException):
            await auth_service.login(email="alice@example.com", password="Wrong")

    @pytest.mark.asyncio
    async def test_unknown_user_raises(self, auth_service, mock_user_repo):
        mock_user_repo.get_by_email.return_value = None
        with pytest.raises(CredentialsException):
            await auth_service.login(email="ghost@example.com", password="Secret123")


class TestRefresh:
    @pytest.mark.asyncio
    async def test_rotates_token(self, auth_service, mock_user_repo, token_repo):
        user = make_user()
        mock_user_repo.get_by_id.return_value = user

        jwt = JWTService()
        rt, jti = jwt.create_refresh_token(str(user.id))
        token_repo._refresh[jti] = str(user.id)

        pair = await auth_service.refresh(refresh_token=rt)
        assert pair.access_token
        assert jti not in token_repo._refresh   # old JTI rotated out

    @pytest.mark.asyncio
    async def test_replay_attack_raises(self, auth_service, token_repo):
        user = make_user()
        jwt = JWTService()
        rt, _ = jwt.create_refresh_token(str(user.id))
        # JTI not in repo → rejected
        with pytest.raises(TokenRevokedException):
            await auth_service.refresh(refresh_token=rt)


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_token(self, auth_service, mock_user_repo, token_repo):
        user = make_user()
        mock_user_repo.get_by_id.return_value = user
        jwt = JWTService()
        token, _ = jwt.create_access_token(str(user.id), "user")
        result = await auth_service.get_current_user(access_token=token)
        assert result.id == user.id

    @pytest.mark.asyncio
    async def test_denied_token_raises(self, auth_service, mock_user_repo, token_repo):
        user = make_user()
        jwt = JWTService()
        token, jti = jwt.create_access_token(str(user.id), "user")
        token_repo._denied.add(jti)
        with pytest.raises(TokenRevokedException):
            await auth_service.get_current_user(access_token=token)

    @pytest.mark.asyncio
    async def test_logout_all_devices(self, auth_service, mock_user_repo, token_repo):
        user = make_user()
        mock_user_repo.get_by_id.return_value = user

        # Log in from two "devices"
        p1 = await auth_service.login(email="alice@example.com", password="Secret123")
        mock_user_repo.get_by_email.return_value = make_user()
        p2 = await auth_service.login(email="alice@example.com", password="Secret123")

        jwt = JWTService()
        _, jti1 = jwt.create_access_token(str(user.id), "user")
        await auth_service.logout_all_devices(user_id=str(user.id), access_jti=jti1)

        assert len([v for v in token_repo._refresh.values()
                    if v == str(user.id)]) == 0
