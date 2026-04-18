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


async def test_admin_manages_task_tags_and_tasks_accept_only_reference_values(client: AsyncClient) -> None:
    await register_user(client, email="admin-tags@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-tags@example.com", full_name="Nina Analyst")

    admin_token = await login_user(client, email="admin-tags@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    analyst_id = next(
        user["id"] for user in users_response.json() if user["email"] == "analyst-tags@example.com"
    )

    role_response = await client.patch(
        f"/users/{analyst_id}",
        headers=admin_headers,
        json={"role": "ANALYST"},
    )
    assert role_response.status_code == 200

    duplicate_before_create_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "  Reports  "},
    )
    assert duplicate_before_create_response.status_code == 201
    created_tag = duplicate_before_create_response.json()
    assert created_tag["name"] == "Reports"

    duplicate_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "reports"},
    )
    assert duplicate_response.status_code == 409

    analyst_token = await login_user(client, email="analyst-tags@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    task_tags_response = await client.get("/task-tags", headers=analyst_headers)
    assert task_tags_response.status_code == 200
    assert task_tags_response.json() == [{"id": created_tag["id"], "name": "Reports"}]

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Task tags", "description": "Reference values"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    unknown_tag_task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Unknown tag",
            "content": "A task must not accept arbitrary tags.",
            "tags": ["Urgent"],
        },
    )
    assert unknown_tag_task_response.status_code == 422

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Canonical tag",
            "content": "A task must use a tag from the admin directory.",
            "tags": ["reports"],
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]
    assert task_response.json()["tags"] == ["Reports"]

    rule_response = await client.post(
        f"/projects/{project_id}/rules",
        headers=admin_headers,
        json={
            "title": "Reports rule",
            "description": "Rules can use only reference task tags.",
            "applies_to_tags": ["Reports"],
            "is_active": True,
        },
    )
    assert rule_response.status_code == 201

    rename_response = await client.patch(
        f"/admin/task-tags/{created_tag['id']}",
        headers=admin_headers,
        json={"name": "Analytics reports"},
    )
    assert rename_response.status_code == 200
    assert rename_response.json()["name"] == "Analytics reports"

    task_after_rename_response = await client.get(
        f"/projects/{project_id}/tasks/{task_id}",
        headers=analyst_headers,
    )
    assert task_after_rename_response.status_code == 200
    assert task_after_rename_response.json()["tags"] == ["Analytics reports"]

    rules_after_rename_response = await client.get(
        f"/projects/{project_id}/rules",
        headers=admin_headers,
    )
    assert rules_after_rename_response.status_code == 200
    assert rules_after_rename_response.json()[0]["applies_to_tags"] == ["Analytics reports"]

    delete_in_use_response = await client.delete(
        f"/admin/task-tags/{created_tag['id']}",
        headers=admin_headers,
    )
    assert delete_in_use_response.status_code == 409
