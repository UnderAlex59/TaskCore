from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.schemas.task import TaskTagSuggestionItem, TaskTagSuggestionResponse

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


async def set_role(
    client: AsyncClient,
    *,
    admin_headers: dict[str, str],
    email: str,
    role: str,
) -> str:
    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    user_id = next(user["id"] for user in users_response.json() if user["email"] == email)
    role_response = await client.patch(
        f"/users/{user_id}",
        headers=admin_headers,
        json={"role": role},
    )
    assert role_response.status_code == 200
    return user_id


async def test_project_tag_directory_controls_tasks_rules_and_global_rename(client: AsyncClient) -> None:
    await register_user(client, email="admin-tags@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-tags@example.com", full_name="Nina Analyst")

    admin_token = await login_user(client, email="admin-tags@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await set_role(
        client,
        admin_headers=admin_headers,
        email="analyst-tags@example.com",
        role="ANALYST",
    )

    create_global_tag_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "  Reports  "},
    )
    assert create_global_tag_response.status_code == 201
    created_tag = create_global_tag_response.json()
    assert created_tag["name"] == "Reports"

    duplicate_global_tag_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "reports"},
    )
    assert duplicate_global_tag_response.status_code == 409

    analyst_token = await login_user(client, email="analyst-tags@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Task tags", "description": "Reference values"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    add_project_tag_response = await client.post(
        f"/projects/{project_id}/task-tags",
        headers=analyst_headers,
        json={"name": "reports"},
    )
    assert add_project_tag_response.status_code == 201
    assert add_project_tag_response.json() == {"id": created_tag["id"], "name": "Reports"}

    project_tags_response = await client.get(
        f"/projects/{project_id}/task-tags",
        headers=analyst_headers,
    )
    assert project_tags_response.status_code == 200
    assert project_tags_response.json() == [{"id": created_tag["id"], "name": "Reports"}]

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
            "content": "A task must use a tag from the project directory.",
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
            "description": "Rules can use only project directory tags.",
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

    project_tags_after_rename_response = await client.get(
        f"/projects/{project_id}/task-tags",
        headers=analyst_headers,
    )
    assert project_tags_after_rename_response.status_code == 200
    assert project_tags_after_rename_response.json() == [
        {"id": created_tag["id"], "name": "Analytics reports"}
    ]

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

    remove_project_tag_response = await client.delete(
        f"/projects/{project_id}/task-tags/{created_tag['id']}",
        headers=analyst_headers,
    )
    assert remove_project_tag_response.status_code == 409

    delete_in_use_response = await client.delete(
        f"/admin/task-tags/{created_tag['id']}",
        headers=admin_headers,
    )
    assert delete_in_use_response.status_code == 409


async def test_suggest_tags_uses_project_directory_and_is_available_to_analyst(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await register_user(client, email="admin-suggest@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-suggest@example.com", full_name="Nina Analyst")
    await register_user(client, email="developer-suggest@example.com", full_name="Dan Developer")

    admin_token = await login_user(client, email="admin-suggest@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    await set_role(
        client,
        admin_headers=admin_headers,
        email="analyst-suggest@example.com",
        role="ANALYST",
    )
    developer_id = await set_role(
        client,
        admin_headers=admin_headers,
        email="developer-suggest@example.com",
        role="DEVELOPER",
    )

    analyst_token = await login_user(client, email="analyst-suggest@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Suggestion project", "description": "LLM tags"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    add_member_response = await client.post(
        f"/projects/{project_id}/members",
        headers=analyst_headers,
        json={"user_id": developer_id, "role": "DEVELOPER"},
    )
    assert add_member_response.status_code == 201

    for tag_name in ["Reports", "Billing", "Security"]:
        response = await client.post(
            f"/projects/{project_id}/task-tags",
            headers=analyst_headers,
            json={"name": tag_name},
        )
        assert response.status_code == 201

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Prepare monthly billing report",
            "content": "Need a monthly report with export, totals and reconciliation details.",
            "tags": [],
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    async def fake_run_task_tag_suggestion_graph(**kwargs) -> TaskTagSuggestionResponse:  # type: ignore[no-untyped-def]
        assert kwargs["available_tags"] == ["Billing", "Reports", "Security"]
        return TaskTagSuggestionResponse(
            suggestions=[
                TaskTagSuggestionItem(
                    tag="Billing",
                    confidence=0.94,
                    reason="Задача про биллинг и отчётность.",
                ),
                TaskTagSuggestionItem(
                    tag="Reports",
                    confidence=0.88,
                    reason="Нужно сформировать отчёт.",
                ),
            ],
            generated_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )

    monkeypatch.setattr("app.services.task_service.run_task_tag_suggestion_graph", fake_run_task_tag_suggestion_graph)

    suggest_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/suggest-tags",
        headers=analyst_headers,
        json={
            "title": "Prepare monthly billing report",
            "content": "Need a monthly report with export, totals and reconciliation details.",
            "current_tags": [],
        },
    )
    assert suggest_response.status_code == 200
    assert suggest_response.json()["suggestions"] == [
        {
            "tag": "Billing",
            "confidence": 0.94,
            "reason": "Задача про биллинг и отчётность.",
        },
        {
            "tag": "Reports",
            "confidence": 0.88,
            "reason": "Нужно сформировать отчёт.",
        },
    ]

    developer_token = await login_user(client, email="developer-suggest@example.com")
    developer_headers = {"Authorization": f"Bearer {developer_token}"}
    forbidden_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/suggest-tags",
        headers=developer_headers,
        json={
            "title": "Prepare monthly billing report",
            "content": "Need a monthly report with export, totals and reconciliation details.",
            "current_tags": [],
        },
    )
    assert forbidden_response.status_code == 403
