from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

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


async def login_user(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "StrongPass1"},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


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

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as attacker:
        attacker.cookies.set("refresh_token", compromised_token)
        attack_response = await attacker.post("/auth/refresh")
        assert attack_response.status_code == 401
        assert "повторное использование токена" in attack_response.json()["detail"].lower()

    follow_up = await client.post("/auth/refresh")
    assert follow_up.status_code == 401


async def test_user_can_delete_own_account(client: AsyncClient) -> None:
    await register_user(client, email="admin-delete-self@example.com")
    await register_user(client, email="self-delete@example.com")
    access_token = await login_user(client, "self-delete@example.com")

    delete_response = await client.delete(
        "/users/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert delete_response.status_code == 204

    me_response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_response.status_code == 401

    login_response = await client.post(
        "/auth/login",
        json={"email": "self-delete@example.com", "password": "StrongPass1"},
    )
    assert login_response.status_code == 401

    register_again_response = await client.post(
        "/auth/register",
        json={
            "email": "self-delete@example.com",
            "password": "StrongPass1",
            "full_name": "Self Delete",
        },
    )
    assert register_again_response.status_code == 201


async def test_admin_can_delete_any_account(client: AsyncClient) -> None:
    await register_user(client, email="admin-delete-user@example.com")
    await register_user(client, email="target-delete@example.com")
    admin_token = await login_user(client, "admin-delete-user@example.com")
    target_token = await login_user(client, "target-delete@example.com")

    users_response = await client.get(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    target_id = next(
        user["id"]
        for user in users_response.json()
        if user["email"] == "target-delete@example.com"
    )

    delete_response = await client.delete(
        f"/users/{target_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_response.status_code == 204

    deleted_me_response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {target_token}"},
    )
    assert deleted_me_response.status_code == 401

    users_after_delete = await client.get(
        "/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert all(user["id"] != target_id for user in users_after_delete.json())


async def test_cannot_delete_last_active_admin(client: AsyncClient) -> None:
    await register_user(client, email="last-admin@example.com")
    admin_token = await login_user(client, "last-admin@example.com")

    delete_response = await client.delete(
        "/users/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_response.status_code == 409
    assert "последнего активного администратора" in delete_response.json()["detail"]
