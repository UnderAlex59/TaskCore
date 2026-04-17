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


async def test_task_lifecycle_uses_task_team_and_chat_access_rules(client: AsyncClient) -> None:
    await register_user(client, email="admin@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst@example.com", full_name="Nina Analyst")
    await register_user(client, email="developer@example.com", full_name="Dan Developer")
    await register_user(client, email="tester@example.com", full_name="Tina Tester")
    await register_user(client, email="outsider@example.com", full_name="Oscar Outsider")

    admin_token = await login_user(client, email="admin@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    users_by_email = {user["email"]: user for user in users_response.json()}

    analyst_id = users_by_email["analyst@example.com"]["id"]
    developer_id = users_by_email["developer@example.com"]["id"]
    tester_id = users_by_email["tester@example.com"]["id"]
    outsider_id = users_by_email["outsider@example.com"]["id"]

    update_role_cases = [
        (analyst_id, "ANALYST"),
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
        (outsider_id, "DEVELOPER"),
    ]
    for user_id, role in update_role_cases:
        response = await client.patch(
            f"/users/{user_id}",
            headers=admin_headers,
            json={"role": role},
        )
        assert response.status_code == 200
        assert response.json()["role"] == role

    analyst_token = await login_user(client, email="analyst@example.com")
    developer_token = await login_user(client, email="developer@example.com")
    tester_token = await login_user(client, email="tester@example.com")
    outsider_token = await login_user(client, email="outsider@example.com")

    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    developer_headers = {"Authorization": f"Bearer {developer_token}"}
    tester_headers = {"Authorization": f"Bearer {tester_token}"}
    outsider_headers = {"Authorization": f"Bearer {outsider_token}"}

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Workflow project", "description": "Task lifecycle"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    member_cases = [
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
        (outsider_id, "DEVELOPER"),
    ]
    for user_id, role in member_cases:
        response = await client.post(
            f"/projects/{project_id}/members",
            headers=analyst_headers,
            json={"user_id": user_id, "role": role},
        )
        assert response.status_code == 201
        assert response.json()["role"] == role

    rejected_create_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Legacy assignee field",
            "content": "When the task is created, the API must reject the removed field assigned_to immediately.",
            "tags": ["workflow"],
            "assigned_to": developer_id,
        },
    )
    assert rejected_create_response.status_code == 422

    create_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Preserve report filters",
            "content": (
                "When an analyst opens the report builder, the system must preserve selected filters "
                "for the current project and then restore them after a page refresh."
            ),
            "tags": ["reports"],
        },
    )
    assert create_response.status_code == 201
    created_task = create_response.json()
    task_id = created_task["id"]
    assert created_task["status"] == "draft"
    assert created_task["analyst_id"] == analyst_id
    assert created_task["developer_id"] is None
    assert created_task["tester_id"] is None

    preapprove_chat_response = await client.get(
        f"/tasks/{task_id}/messages",
        headers=developer_headers,
    )
    assert preapprove_chat_response.status_code == 403

    validate_response = await client.post(
        f"/tasks/{task_id}/validate",
        headers=analyst_headers,
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["verdict"] == "approved"

    task_after_validate_response = await client.get(
        f"/projects/{project_id}/tasks/{task_id}",
        headers=analyst_headers,
    )
    assert task_after_validate_response.status_code == 200
    assert task_after_validate_response.json()["status"] == "awaiting_approval"

    developer_approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=developer_headers,
        json={"developer_id": developer_id, "tester_id": tester_id},
    )
    assert developer_approve_response.status_code == 403

    same_person_approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={"developer_id": developer_id, "tester_id": developer_id},
    )
    assert same_person_approve_response.status_code == 422

    wrong_role_approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={"developer_id": developer_id, "tester_id": outsider_id},
    )
    assert wrong_role_approve_response.status_code == 422

    approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={"developer_id": developer_id, "tester_id": tester_id},
    )
    assert approve_response.status_code == 200
    approved_task = approve_response.json()
    assert approved_task["status"] == "ready_for_dev"
    assert approved_task["developer_id"] == developer_id
    assert approved_task["tester_id"] == tester_id

    outsider_chat_response = await client.get(
        f"/tasks/{task_id}/messages",
        headers=outsider_headers,
    )
    assert outsider_chat_response.status_code == 403

    developer_chat_response = await client.get(
        f"/tasks/{task_id}/messages",
        headers=developer_headers,
    )
    assert developer_chat_response.status_code == 200
    developer_messages = developer_chat_response.json()
    assert any("Команда задачи сформирована" in message["content"] for message in developer_messages)

    send_message_response = await client.post(
        f"/tasks/{task_id}/messages",
        headers=developer_headers,
        json={"content": "Команда приняла задачу в работу."},
    )
    assert send_message_response.status_code == 201
    assert send_message_response.json()[0]["author_id"] == developer_id

    tester_chat_response = await client.get(
        f"/tasks/{task_id}/messages",
        headers=tester_headers,
    )
    assert tester_chat_response.status_code == 200
    assert any(
        message["content"] == "Команда приняла задачу в работу."
        for message in tester_chat_response.json()
    )
