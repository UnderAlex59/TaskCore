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


async def test_task_can_pass_second_review_and_full_delivery_flow(client: AsyncClient) -> None:
    await register_user(client, email="admin-review@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-review@example.com", full_name="Nina Analyst")
    await register_user(client, email="reviewer-review@example.com", full_name="Ira Reviewer")
    await register_user(client, email="developer-review@example.com", full_name="Dan Developer")
    await register_user(client, email="tester-review@example.com", full_name="Tina Tester")

    admin_token = await login_user(client, email="admin-review@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    users_by_email = {user["email"]: user for user in users_response.json()}

    analyst_id = users_by_email["analyst-review@example.com"]["id"]
    reviewer_id = users_by_email["reviewer-review@example.com"]["id"]
    developer_id = users_by_email["developer-review@example.com"]["id"]
    tester_id = users_by_email["tester-review@example.com"]["id"]

    for user_id, role in [
        (analyst_id, "ANALYST"),
        (reviewer_id, "ANALYST"),
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.patch(
            f"/users/{user_id}",
            headers=admin_headers,
            json={"role": role},
        )
        assert response.status_code == 200

    analyst_token = await login_user(client, email="analyst-review@example.com")
    reviewer_token = await login_user(client, email="reviewer-review@example.com")
    developer_token = await login_user(client, email="developer-review@example.com")
    tester_token = await login_user(client, email="tester-review@example.com")

    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    reviewer_headers = {"Authorization": f"Bearer {reviewer_token}"}
    developer_headers = {"Authorization": f"Bearer {developer_token}"}
    tester_headers = {"Authorization": f"Bearer {tester_token}"}

    tag_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "workflow"},
    )
    assert tag_response.status_code == 201

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Review flow", "description": "Second analyst review"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    for user_id, role in [
        (reviewer_id, "ANALYST"),
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.post(
            f"/projects/{project_id}/members",
            headers=analyst_headers,
            json={"user_id": user_id, "role": role},
        )
        assert response.status_code == 201

    create_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Workflow gate",
            "content": "После ревью задача должна последовательно пройти разработку и тестирование.",
            "tags": ["workflow"],
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]

    validate_response = await client.post(
        f"/tasks/{task_id}/validate",
        headers=analyst_headers,
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["verdict"] == "approved"

    configure_review_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={
            "developer_id": developer_id,
            "tester_id": tester_id,
            "reviewer_analyst_id": reviewer_id,
        },
    )
    assert configure_review_response.status_code == 200
    configured_task = configure_review_response.json()
    assert configured_task["status"] == "awaiting_approval"
    assert configured_task["reviewer_analyst_id"] == reviewer_id
    assert configured_task["reviewer_approved_at"] is None

    reviewer_chat_response = await client.get(
        f"/tasks/{task_id}/messages",
        headers=reviewer_headers,
    )
    assert reviewer_chat_response.status_code == 200

    reviewer_approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=reviewer_headers,
        json={},
    )
    assert reviewer_approve_response.status_code == 200
    reviewed_task = reviewer_approve_response.json()
    assert reviewed_task["status"] == "ready_for_dev"
    assert reviewed_task["reviewer_approved_at"] is not None

    start_development_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/start-development",
        headers=developer_headers,
    )
    assert start_development_response.status_code == 200
    assert start_development_response.json()["status"] == "in_progress"

    ready_for_testing_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/ready-for-testing",
        headers=developer_headers,
    )
    assert ready_for_testing_response.status_code == 200
    assert ready_for_testing_response.json()["status"] == "ready_for_testing"

    start_testing_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/start-testing",
        headers=tester_headers,
    )
    assert start_testing_response.status_code == 200
    assert start_testing_response.json()["status"] == "testing"

    complete_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/complete",
        headers=tester_headers,
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "done"
