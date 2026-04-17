from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.requires_db


async def register_user(
    client: AsyncClient,
    *,
    email: str,
    full_name: str,
    password: str = "StrongPass1",
) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
        },
    )

    assert response.status_code == 201


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = "StrongPass1",
) -> str:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )

    assert response.status_code == 200
    return response.json()["access_token"]


async def test_project_manager_can_add_member(client: AsyncClient) -> None:
    await register_user(
        client,
        email="manager@example.com",
        full_name="Mia Manager",
    )
    await register_user(
        client,
        email="developer@example.com",
        full_name="Dev Member",
    )

    access_token = await login_user(client, email="manager@example.com")
    auth_headers = {"Authorization": f"Bearer {access_token}"}

    project_response = await client.post(
        "/projects",
        headers=auth_headers,
        json={"name": "Integration project", "description": "Team workspace"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    users_response = await client.get("/users", headers=auth_headers)
    assert users_response.status_code == 200
    developer = next(
        user for user in users_response.json() if user["email"] == "developer@example.com"
    )

    add_member_response = await client.post(
        f"/projects/{project_id}/members",
        headers=auth_headers,
        json={"user_id": developer["id"], "role": "DEVELOPER"},
    )

    assert add_member_response.status_code == 201
    assert add_member_response.json() == {
        "project_id": project_id,
        "user_id": developer["id"],
        "role": "DEVELOPER",
        "joined_at": add_member_response.json()["joined_at"],
        "full_name": "Dev Member",
        "email": "developer@example.com",
        "global_role": "DEVELOPER",
    }
