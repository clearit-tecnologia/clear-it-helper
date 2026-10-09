from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from clear_helper.config import Settings
from clear_helper.models import Role, User
from clear_helper.security import create_access_token, decode_access_token
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, JWT_SECRET


async def _login(client: httpx.AsyncClient, email: str, password: str) -> httpx.Response:
    return await client.post("/auth/login", json={"email": email, "password": password})


async def test_login_success_returns_token(
    client: httpx.AsyncClient, admin: User, settings: Settings
) -> None:
    response = await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_expires_minutes * 60
    claims = decode_access_token(body["access_token"], secret=JWT_SECRET)
    assert claims.sub == admin.id
    assert claims.tid == admin.tenant_id
    assert claims.role is Role.ADMIN


async def test_login_email_is_case_insensitive(client: httpx.AsyncClient, admin: User) -> None:
    response = await _login(client, "  ADMIN@ClearIT.example ", ADMIN_PASSWORD)
    assert response.status_code == 200


async def test_login_wrong_password_returns_401(client: httpx.AsyncClient, admin: User) -> None:
    response = await _login(client, ADMIN_EMAIL, "wrong-password")
    assert response.status_code == 401


async def test_login_unknown_user_returns_401(client: httpx.AsyncClient, admin: User) -> None:
    response = await _login(client, "nobody@clearit.example", ADMIN_PASSWORD)
    assert response.status_code == 401


async def test_login_inactive_user_returns_401(
    client: httpx.AsyncClient, admin: User, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    async with sessionmaker() as session:
        user = await session.get(User, admin.id)
        assert user is not None
        user.is_active = False
        await session.commit()

    response = await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert response.status_code == 401


async def test_login_invalid_body_returns_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/auth/login", json={"email": ADMIN_EMAIL})
    assert response.status_code == 422


async def test_me_returns_user_and_tenant(client: httpx.AsyncClient, admin: User) -> None:
    token = (await _login(client, ADMIN_EMAIL, ADMIN_PASSWORD)).json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == {
        "id": str(admin.id),
        "email": ADMIN_EMAIL,
        "role": "admin",
        "tenant": {"id": str(admin.tenant_id), "name": "ClearIT", "slug": "clearit"},
    }


async def test_me_without_token_returns_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_with_invalid_token_returns_401(client: httpx.AsyncClient) -> None:
    response = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


async def test_me_rejects_token_from_another_tenant(client: httpx.AsyncClient, admin: User) -> None:
    # Valid signature and user id, but the tenant claim does not match the user's tenant.
    token = create_access_token(
        user_id=admin.id,
        tenant_id=uuid.uuid4(),
        role=Role.ADMIN,
        secret=JWT_SECRET,
        expires_minutes=5,
    )
    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
