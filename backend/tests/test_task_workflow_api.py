from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.llm_runtime_service import LLMInvocationResult

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

    for tag_name in ["workflow", "reports"]:
        response = await client.post(
            "/admin/task-tags",
            headers=admin_headers,
            json={"name": tag_name},
        )
        assert response.status_code == 201

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
            "content": (
                "When the task is created, the API must reject "
                "the removed field assigned_to immediately."
            ),
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
                "When an analyst opens the report builder, the system must preserve "
                "selected filters "
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
    assert any(
        "Команда задачи сформирована" in message["content"]
        for message in developer_messages
    )

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


async def test_background_question_does_not_create_agent_reply(client: AsyncClient) -> None:
    await register_user(client, email="admin-bg@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-bg@example.com", full_name="Nina Analyst")
    await register_user(client, email="developer-bg@example.com", full_name="Dan Developer")
    await register_user(client, email="tester-bg@example.com", full_name="Tina Tester")

    admin_token = await login_user(client, email="admin-bg@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    users_by_email = {user["email"]: user for user in users_response.json()}

    analyst_id = users_by_email["analyst-bg@example.com"]["id"]
    developer_id = users_by_email["developer-bg@example.com"]["id"]
    tester_id = users_by_email["tester-bg@example.com"]["id"]

    for user_id, role in [
        (analyst_id, "ANALYST"),
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.patch(
            f"/users/{user_id}",
            headers=admin_headers,
            json={"role": role},
        )
        assert response.status_code == 200

    analyst_token = await login_user(client, email="analyst-bg@example.com")
    developer_token = await login_user(client, email="developer-bg@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    developer_headers = {"Authorization": f"Bearer {developer_token}"}

    tag_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "chat"},
    )
    assert tag_response.status_code == 201

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Background chat", "description": "Chat routing"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    for user_id, role in [
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.post(
            f"/projects/{project_id}/members",
            headers=analyst_headers,
            json={"user_id": user_id, "role": role},
        )
        assert response.status_code == 201

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Task-aware chat",
            "content": (
                "When the team discusses the task, the assistant must answer only when the message "
                "is related to the task context and should stay silent for background questions."
            ),
            "tags": ["chat"],
        },
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    validate_response = await client.post(
        f"/tasks/{task_id}/validate",
        headers=analyst_headers,
    )
    assert validate_response.status_code == 200

    approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={"developer_id": developer_id, "tester_id": tester_id},
    )
    assert approve_response.status_code == 200

    send_message_response = await client.post(
        f"/tasks/{task_id}/messages",
        headers=developer_headers,
        json={"content": "Как погода сегодня?"},
    )
    assert send_message_response.status_code == 201
    created_messages = send_message_response.json()
    assert len(created_messages) == 1
    assert created_messages[0]["author_id"] == developer_id
    assert created_messages[0]["agent_name"] is None


async def test_low_confidence_task_question_is_saved_for_validation_backlog(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await register_user(client, email="admin-low@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-low@example.com", full_name="Nina Analyst")
    await register_user(client, email="developer-low@example.com", full_name="Dan Developer")
    await register_user(client, email="tester-low@example.com", full_name="Tina Tester")

    admin_token = await login_user(client, email="admin-low@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    users_by_email = {user["email"]: user for user in users_response.json()}

    analyst_id = users_by_email["analyst-low@example.com"]["id"]
    developer_id = users_by_email["developer-low@example.com"]["id"]
    tester_id = users_by_email["tester-low@example.com"]["id"]

    for user_id, role in [
        (analyst_id, "ANALYST"),
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.patch(
            f"/users/{user_id}",
            headers=admin_headers,
            json={"role": role},
        )
        assert response.status_code == 200

    analyst_token = await login_user(client, email="analyst-low@example.com")
    developer_token = await login_user(client, email="developer-low@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}
    developer_headers = {"Authorization": f"Bearer {developer_token}"}

    tag_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "integration"},
    )
    assert tag_response.status_code == 201

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Low confidence chat", "description": "Validation backlog"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    for user_id, role in [
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.post(
            f"/projects/{project_id}/members",
            headers=analyst_headers,
            json={"user_id": user_id, "role": role},
        )
        assert response.status_code == 201

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "Status sync contract",
            "content": (
                "When an operator changes the order status in the CRM, the backend should "
                "persist the new value, publish an event for downstream services and expose "
                "the updated status in the UI within one refresh cycle."
            ),
            "tags": ["integration"],
        },
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    validate_response = await client.post(
        f"/tasks/{task_id}/validate",
        headers=analyst_headers,
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["verdict"] == "approved"

    approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={"developer_id": developer_id, "tester_id": tester_id},
    )
    assert approve_response.status_code == 200

    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        if kwargs["agent_key"] == "qa-planner":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"analysis_mode":"deep","needs_rag":true,'
                    '"needs_verification":true,'
                    '"retrieval_query":"терминальные статусы и повторная синхронизация",'
                    '"retrieval_limit":4,'
                    '"focus_points":["terminal statuses","sync initiator"],'
                    '"canonical_question_hint":"Какие статусы считаются терминальными '
                    'и кто инициирует повторную синхронизацию?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=25,
                prompt_tokens=8,
                completion_tokens=10,
                total_tokens=18,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-answer":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"answer":"В текущем требовании не описано, какие статусы считаются '
                    'терминальными и кто инициирует повторную синхронизацию.",'
                    '"confidence":"low",'
                    '"canonical_question":"Какие статусы считаются терминальными '
                    'и кто инициирует повторную синхронизацию?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=75,
                prompt_tokens=12,
                completion_tokens=18,
                total_tokens=30,
                estimated_cost_usd=None,
            )
        raise AssertionError(f"Unexpected agent key: {kwargs['agent_key']}")

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )

    send_message_response = await client.post(
        f"/tasks/{task_id}/messages",
        headers=developer_headers,
        json={
            "content": (
                "Какие статусы считаются терминальными и кто запускает "
                "повторную синхронизацию?"
            )
        },
    )
    assert send_message_response.status_code == 201
    assert send_message_response.json()[0]["author_id"] == developer_id

    messages_response = await client.get(
        f"/tasks/{task_id}/messages",
        headers=developer_headers,
    )
    assert messages_response.status_code == 200
    qa_message = next(
        message
        for message in messages_response.json()
        if message["agent_name"] == "QAAgent"
    )
    assert qa_message["source_ref"]["validation_backlog_saved"] is True
    assert qa_message["source_ref"]["answer_confidence"] == "low"
    assert "Вопрос сохранён в базе вопросов" in qa_message["content"]

    backlog_response = await client.get(
        "/admin/validation/questions",
        headers=admin_headers,
        params={"project_id": project_id, "search": "терминальными"},
    )
    assert backlog_response.status_code == 200
    backlog_item = next(
        item for item in backlog_response.json()["items"] if item["task_id"] == task_id
    )
    assert (
        backlog_item["question_text"]
        == "Какие статусы считаются терминальными и кто инициирует повторную синхронизацию?"
    )

    task_response = await client.get(
        f"/projects/{project_id}/tasks/{task_id}",
        headers=analyst_headers,
    )
    assert task_response.status_code == 200
    assert (
        "Какие статусы считаются терминальными и кто инициирует повторную синхронизацию?"
        in task_response.json()["validation_result"]["questions"]
    )


async def test_project_validation_node_settings_affect_task_validation(client: AsyncClient) -> None:
    await register_user(client, email="admin-nodes@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-nodes@example.com", full_name="Nina Analyst")

    admin_token = await login_user(client, email="admin-nodes@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    analyst_id = next(
        user["id"] for user in users_response.json() if user["email"] == "analyst-nodes@example.com"
    )

    role_response = await client.patch(
        f"/users/{analyst_id}",
        headers=admin_headers,
        json={"role": "ANALYST"},
    )
    assert role_response.status_code == 200

    analyst_token = await login_user(client, email="analyst-nodes@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Validation switches", "description": "Per-project graph settings"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    update_response = await client.patch(
        f"/projects/{project_id}",
        headers=admin_headers,
        json={
            "validation_node_settings": {
                "core_rules": False,
                "custom_rules": False,
                "context_questions": False,
            }
        },
    )
    assert update_response.status_code == 200

    create_task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "API",
            "content": "Коротко.",
            "tags": [],
        },
    )
    assert create_task_response.status_code == 201
    task_id = create_task_response.json()["id"]

    validate_response = await client.post(
        f"/tasks/{task_id}/validate",
        headers=analyst_headers,
    )
    assert validate_response.status_code == 200
    assert validate_response.json()["verdict"] == "approved"
    assert validate_response.json()["issues"] == []
    assert validate_response.json()["questions"] == []


async def test_task_can_be_edited_after_approval_and_requires_explicit_embedding_commit(
    client: AsyncClient,
) -> None:
    await register_user(client, email="admin-commit@example.com", full_name="Alice Admin")
    await register_user(client, email="analyst-commit@example.com", full_name="Nina Analyst")
    await register_user(client, email="developer-commit@example.com", full_name="Dan Developer")
    await register_user(client, email="tester-commit@example.com", full_name="Tina Tester")

    admin_token = await login_user(client, email="admin-commit@example.com")
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    users_by_email = {user["email"]: user for user in users_response.json()}

    analyst_id = users_by_email["analyst-commit@example.com"]["id"]
    developer_id = users_by_email["developer-commit@example.com"]["id"]
    tester_id = users_by_email["tester-commit@example.com"]["id"]

    for user_id, role in [
        (analyst_id, "ANALYST"),
        (developer_id, "DEVELOPER"),
        (tester_id, "TESTER"),
    ]:
        response = await client.patch(
            f"/users/{user_id}",
            headers=admin_headers,
            json={"role": role},
        )
        assert response.status_code == 200

    analyst_token = await login_user(client, email="analyst-commit@example.com")
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    tag_response = await client.post(
        "/admin/task-tags",
        headers=admin_headers,
        json={"name": "delivery"},
    )
    assert tag_response.status_code == 201

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Commit flow", "description": "Post-approval edits"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    for user_id, role in [
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
            "title": "Shared delivery notes",
            "content": "Первичная версия требования для передачи в разработку.",
            "tags": ["delivery"],
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

    approve_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/approve",
        headers=analyst_headers,
        json={"developer_id": developer_id, "tester_id": tester_id},
    )
    assert approve_response.status_code == 200
    approved_task = approve_response.json()
    assert approved_task["status"] == "ready_for_dev"
    assert approved_task["embeddings_stale"] is False
    assert approved_task["indexed_at"] is not None

    update_response = await client.patch(
        f"/projects/{project_id}/tasks/{task_id}",
        headers=analyst_headers,
        json={
            "content": (
                "Первичная версия требования для передачи в разработку. "
                "Добавили отдельный блок про контроль ошибок."
            )
        },
    )
    assert update_response.status_code == 200
    updated_task = update_response.json()
    assert updated_task["status"] == "ready_for_dev"
    assert updated_task["validation_result"] is not None
    assert updated_task["embeddings_stale"] is True

    commit_response = await client.post(
        f"/projects/{project_id}/tasks/{task_id}/commit",
        headers=analyst_headers,
    )
    assert commit_response.status_code == 200
    committed_task = commit_response.json()
    assert committed_task["status"] == "ready_for_dev"
    assert committed_task["embeddings_stale"] is False
    assert committed_task["indexed_at"] is not None
