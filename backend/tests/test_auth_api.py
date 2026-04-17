from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest

from main import app

pytestmark = pytest.mark.requires_db


async def register_user(client: AsyncClient, email: str = "analyst@example.com") -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "StrongPass1",
            "full_name": "Alex Analyst",
        },
    )

    assert response.status_code == 201


async def test_auth_lifecycle(client: AsyncClient) -> None:
    await register_user(client)

    login_response = await client.post(
        "/auth/login",
        json={"email": "analyst@example.com", "password": "StrongPass1"},
    )
    assert login_response.status_code == 200
    access_token = login_response.json()["access_token"]
    assert client.cookies.get("refresh_token")

    me_response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "analyst@example.com"

    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 200
    refreshed_access_token = refresh_response.json()["access_token"]
    assert refreshed_access_token != access_token

    sessions_response = await client.get(
        "/auth/sessions",
        headers={"Authorization": f"Bearer {refreshed_access_token}"},
    )
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) == 1

    revoke_response = await client.delete(
        f"/auth/sessions/{sessions[0]['id']}",
        headers={"Authorization": f"Bearer {refreshed_access_token}"},
    )
    assert revoke_response.status_code == 204

    logout_response = await client.post("/auth/logout")
    assert logout_response.status_code == 204


async def test_refresh_token_reuse_revokes_token_family(client: AsyncClient) -> None:
    await register_user(client, email="reuse@example.com")
    login_response = await client.post(
        "/auth/login",
        json={"email": "reuse@example.com", "password": "StrongPass1"},
    )
    assert login_response.status_code == 200

    compromised_token = client.cookies.get("refresh_token")
    assert compromised_token is not None

    refresh_response = await client.post("/auth/refresh")
    assert refresh_response.status_code == 200

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as attacker:
        attacker.cookies.set("refresh_token", compromised_token)
        attack_response = await attacker.post("/auth/refresh")
        assert attack_response.status_code == 401
        assert "reuse" in attack_response.json()["detail"].lower()

    follow_up = await client.post("/auth/refresh")
    assert follow_up.status_code == 401
