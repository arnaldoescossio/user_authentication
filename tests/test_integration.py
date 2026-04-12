"""
Integration tests — full HTTP round-trips through the real FastAPI app.
No mocks except DB (SQLite) and Redis (FakeTokenCache via conftest.py).

Run with: pytest tests/test_integration.py -v --asyncio-mode=auto
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ------------------------------------------------------------------ #
#  Register                                                            #
# ------------------------------------------------------------------ #

class TestRegister:
    @pytest.mark.asyncio
    async def test_register_returns_201(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/auth/register", json={
            "email":    "new@example.com",
            "username": "newuser",
            "password": "Secret123",
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"]    == "new@example.com"
        assert body["username"] == "newuser"
        assert body["role"]     == "user"
        assert "hashed_password" not in body  # never leak

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, async_client: AsyncClient, registered_user):
        resp = await async_client.post("/api/v1/auth/register", json={
            "email":    "testuser@example.com",
            "username": "other",
            "password": "Secret123",
        })
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_register_weak_password_returns_422(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/auth/register", json={
            "email":    "weak@example.com",
            "username": "weakuser",
            "password": "short",          # too short, no uppercase, no digit
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_email_returns_422(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/auth/register", json={
            "email":    "not-an-email",
            "username": "user2",
            "password": "Secret123",
        })
        assert resp.status_code == 422


# ------------------------------------------------------------------ #
#  Login                                                               #
# ------------------------------------------------------------------ #

class TestLogin:
    @pytest.mark.asyncio
    async def test_login_returns_tokens(self, async_client: AsyncClient, registered_user):
        resp = await async_client.post("/api/v1/auth/login", json={
            "email":    "testuser@example.com",
            "password": "Secret123",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token"  in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_wrong_password_returns_401(self, async_client: AsyncClient, registered_user):
        resp = await async_client.post("/api/v1/auth/login", json={
            "email":    "testuser@example.com",
            "password": "WrongPass",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_unknown_email_returns_401(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/auth/login", json={
            "email":    "ghost@example.com",
            "password": "Secret123",
        })
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Token refresh                                                       #
# ------------------------------------------------------------------ #

class TestRefresh:
    @pytest.mark.asyncio
    async def test_refresh_returns_new_tokens(self, async_client: AsyncClient, registered_user):
        login = await async_client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com", "password": "Secret123",
        })
        old_refresh = login.json()["refresh_token"]

        resp = await async_client.post("/api/v1/auth/refresh", json={
            "refresh_token": old_refresh,
        })
        assert resp.status_code == 200
        new_tokens = resp.json()
        assert new_tokens["access_token"]  != login.json()["access_token"]
        assert new_tokens["refresh_token"] != old_refresh

    @pytest.mark.asyncio
    async def test_refresh_replay_attack_returns_401(
        self, async_client: AsyncClient, registered_user
    ):
        """After rotation, re-using the old refresh token must be rejected."""
        login = await async_client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com", "password": "Secret123",
        })
        old_refresh = login.json()["refresh_token"]

        # First use — valid
        r1 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r1.status_code == 200

        # Replay — must fail
        r2 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
        assert r2.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_returns_401(self, async_client: AsyncClient):
        resp = await async_client.post("/api/v1/auth/refresh", json={
            "refresh_token": "not.a.valid.jwt",
        })
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Logout                                                              #
# ------------------------------------------------------------------ #

class TestLogout:
    @pytest.mark.asyncio
    async def test_logout_denies_access_token(
        self, async_client: AsyncClient, registered_user
    ):
        login = await async_client.post("/api/v1/auth/login", json={
            "email": "testuser@example.com", "password": "Secret123",
        })
        tokens  = login.json()
        headers = {"Authorization": f"Bearer {tokens['access_token']}"}

        # Logout
        lo = await async_client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        assert lo.status_code == 204

        # Former access token should now be denied
        me = await async_client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 401


# ------------------------------------------------------------------ #
#  Protected /me                                                       #
# ------------------------------------------------------------------ #

class TestMe:
    @pytest.mark.asyncio
    async def test_me_requires_auth(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_returns_profile(
        self, async_client: AsyncClient, registered_user, auth_headers
    ):
        resp = await async_client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["email"] == "testuser@example.com"

    @pytest.mark.asyncio
    async def test_tampered_token_returns_401(self, async_client: AsyncClient):
        resp = await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer garbage.token.here"},
        )
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Account — password change                                           #
# ------------------------------------------------------------------ #

class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_success(
        self, async_client: AsyncClient, registered_user, auth_headers
    ):
        resp = await async_client.post(
            "/api/v1/account/change-password",
            json={"current_password": "Secret123", "new_password": "NewPass456"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert "successfully" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(
        self, async_client: AsyncClient, registered_user, auth_headers
    ):
        resp = await async_client.post(
            "/api/v1/account/change-password",
            json={"current_password": "WrongPass", "new_password": "NewPass456"},
            headers=auth_headers,
        )
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Account — forgot / reset password                                   #
# ------------------------------------------------------------------ #

class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_forgot_password_always_200(self, async_client: AsyncClient):
        """Must return 200 even for unknown emails (prevent enumeration)."""
        resp = await async_client.post(
            "/api/v1/account/forgot-password",
            json={"email": "nobody@example.com"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_reset_invalid_token_returns_401(self, async_client: AsyncClient):
        resp = await async_client.post(
            "/api/v1/account/reset-password",
            json={"token": "bad-token", "new_password": "NewPass456"},
        )
        assert resp.status_code == 401


# ------------------------------------------------------------------ #
#  Admin — users list                                                  #
# ------------------------------------------------------------------ #

class TestAdminUsers:
    @pytest.mark.asyncio
    async def test_list_users_requires_admin(
        self, async_client: AsyncClient, registered_user, auth_headers
    ):
        resp = await async_client.get("/api/v1/admin/users", headers=auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_users_as_admin(
        self, async_client: AsyncClient, admin_user_and_headers
    ):
        resp = await async_client.get(
            "/api/v1/admin/users",
            headers=admin_user_and_headers["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "total" in body
        assert "pages" in body

    @pytest.mark.asyncio
    async def test_list_users_pagination(
        self, async_client: AsyncClient, admin_user_and_headers
    ):
        resp = await async_client.get(
            "/api/v1/admin/users?page=1&size=1",
            headers=admin_user_and_headers["headers"],
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) <= 1


# ------------------------------------------------------------------ #
#  Health                                                              #
# ------------------------------------------------------------------ #

class TestHealth:
    @pytest.mark.asyncio
    async def test_liveness(self, async_client: AsyncClient):
        resp = await async_client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
