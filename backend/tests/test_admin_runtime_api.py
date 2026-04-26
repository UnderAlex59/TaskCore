from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.services.llm_prompt_service import LLMPromptService
from app.services.llm_runtime_service import LLMInvocationResult

pytestmark = pytest.mark.requires_db


async def register_and_login(
    client: AsyncClient,
    *,
    email: str,
    full_name: str,
) -> str:
    register_response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "StrongPass1",
            "full_name": full_name,
        },
    )
    assert register_response.status_code == 201

    login_response = await client.post(
        "/auth/login",
        json={"email": email, "password": "StrongPass1"},
    )
    assert login_response.status_code == 200
    return str(login_response.json()["access_token"])


@pytest.mark.asyncio
async def test_admin_provider_list_bootstraps_runtime(client: AsyncClient) -> None:
    access_token = await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )

    response = await client.get(
        "/admin/llm/providers",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload == []


@pytest.mark.asyncio
async def test_admin_endpoints_require_admin_role(client: AsyncClient) -> None:
    await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )
    user_token = await register_and_login(
        client,
        email="developer@example.com",
        full_name="Developer User",
    )

    response = await client.get(
        "/admin/llm/providers",
        headers={"Authorization": f"Bearer {user_token}"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_create_test_and_override_provider(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access_token = await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )

    async def fake_test_provider(
        *args: object,  # noqa: ARG001
        **kwargs: object,  # noqa: ARG001
    ) -> LLMInvocationResult:
        return LLMInvocationResult(
            ok=True,
            text="Connectivity OK",
            provider_config_id="provider-1",
            provider_kind="openrouter",
            model="openai/gpt-4o-mini",
            latency_ms=42,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        "app.services.admin_llm_service.LLMRuntimeService.test_provider",
        fake_test_provider,
    )

    create_response = await client.post(
        "/admin/llm/providers",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "name": "OpenRouter experiment",
            "provider_kind": "openrouter",
            "base_url": "",
            "model": "openai/gpt-4o-mini",
            "temperature": 0.1,
            "enabled": False,
            "secret": "router-secret",
        },
    )
    assert create_response.status_code == 201
    provider_id = create_response.json()["id"]

    test_response = await client.post(
        f"/admin/llm/providers/{provider_id}/test",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert test_response.status_code == 200
    assert test_response.json()["ok"] is True

    default_response = await client.post(
        "/admin/llm/runtime/default-provider",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"provider_config_id": provider_id},
    )
    assert default_response.status_code == 200
    assert default_response.json()["is_default"] is True

    override_response = await client.put(
        "/admin/llm/overrides/task-validation",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"provider_config_id": provider_id, "enabled": True},
    )
    assert override_response.status_code == 200
    assert override_response.json()["agent_key"] == "task-validation"
    assert override_response.json()["provider_config_id"] == provider_id

    vision_override_response = await client.put(
        "/admin/llm/overrides/rag-vision",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"provider_config_id": provider_id, "enabled": True},
    )
    assert vision_override_response.status_code == 200
    assert vision_override_response.json()["agent_key"] == "rag-vision"
    assert vision_override_response.json()["provider_config_id"] == provider_id


@pytest.mark.asyncio
async def test_admin_can_list_all_llm_consumers(client: AsyncClient) -> None:
    access_token = await register_and_login(
        client,
        email="admin-llm-consumers@example.com",
        full_name="Admin User",
    )

    response = await client.get(
        "/admin/llm/agents",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    payload = response.json()
    keys = {item["key"] for item in payload}
    assert {
        "qa-planner",
        "qa-answer",
        "qa-verifier",
        "change-tracker",
        "chat-routing",
        "rag-vision",
        "task-validation",
    } <= keys


@pytest.mark.asyncio
async def test_admin_can_run_vision_test_with_uploaded_image(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    access_token = await register_and_login(
        client,
        email="admin-vision-test@example.com",
        full_name="Admin Vision",
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    create_response = await client.post(
        "/admin/llm/providers",
        headers=headers,
        json={
            "name": "Vision provider",
            "provider_kind": "openai",
            "base_url": "",
            "model": "gpt-4o",
            "temperature": 0.2,
            "enabled": True,
            "secret": "vision-secret",
        },
    )
    assert create_response.status_code == 201
    provider_id = create_response.json()["id"]

    async def fake_invoke_vision(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text="Счет №42\nИтого: 15 000 ₽",
            provider_config_id=provider_id,
            provider_kind="openai",
            model="gpt-4o",
            latency_ms=64,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_vision",
        fake_invoke_vision,
    )

    response = await client.post(
        "/admin/llm/vision-test",
        headers=headers,
        data={"prompt": "Извлеки текст без пояснений."},
        files={"file": ("scan.png", b"fake image bytes", "image/png")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["provider_config_id"] == provider_id
    assert payload["provider_name"] == "Vision provider"
    assert payload["provider_kind"] == "openai"
    assert payload["model"] == "gpt-4o"
    assert payload["result_text"] == "Счет №42\nИтого: 15 000 ₽"


@pytest.mark.asyncio
async def test_admin_can_update_and_restore_agent_prompt_config(
    client: AsyncClient,
) -> None:
    access_token = await register_and_login(
        client,
        email="admin-prompts@example.com",
        full_name="Admin User",
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    list_response = await client.get("/admin/llm/prompt-configs", headers=headers)
    assert list_response.status_code == 200
    prompt_configs = list_response.json()
    prompt_keys = {item["prompt_key"] for item in prompt_configs}
    assert {"change-tracker", "task-validation-core"} <= prompt_keys

    updated_description = "Редакция агента для нормализации изменений требований."
    updated_system_prompt = (
        "Ты превращаешь пользовательский запрос в строгую редакцию требования. "
        "Верни JSON с ключами proposal_text и acknowledgement. "
        "Не добавляй текст вне JSON."
    )
    patch_response = await client.patch(
        "/admin/llm/prompt-configs/change-tracker",
        headers=headers,
        json={
            "description": updated_description,
            "system_prompt": updated_system_prompt,
            "enabled": True,
        },
    )
    assert patch_response.status_code == 200
    payload = patch_response.json()
    assert payload["override_enabled"] is True
    assert payload["effective_description"] == updated_description
    assert payload["effective_system_prompt"] == updated_system_prompt
    assert payload["revision"] == 1

    async with AsyncSessionLocal() as db:
        resolved_prompt = await LLMPromptService.resolve_system_prompt(
            db,
            prompt_key="change-tracker",
            default_system_prompt="default prompt",
        )
    assert resolved_prompt == updated_system_prompt

    disabled_response = await client.patch(
        "/admin/llm/prompt-configs/change-tracker",
        headers=headers,
        json={
            "description": updated_description,
            "system_prompt": updated_system_prompt,
            "enabled": False,
        },
    )
    assert disabled_response.status_code == 200
    assert disabled_response.json()["override_enabled"] is False
    assert disabled_response.json()["effective_system_prompt"] != updated_system_prompt

    versions_response = await client.get(
        "/admin/llm/prompt-configs/change-tracker/versions",
        headers=headers,
    )
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert [item["revision"] for item in versions] == [2, 1]

    restore_response = await client.post(
        "/admin/llm/prompt-configs/change-tracker/restore",
        headers=headers,
        json={"version_id": versions[-1]["id"]},
    )
    assert restore_response.status_code == 200
    assert restore_response.json()["revision"] == 3
    assert restore_response.json()["effective_system_prompt"] == updated_system_prompt


@pytest.mark.asyncio
async def test_monitoring_endpoints_return_admin_metrics(client: AsyncClient) -> None:
    access_token = await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )

    summary_response = await client.get(
        "/admin/monitoring/summary",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"range": "7d"},
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["all_time"]["users_total"] == 1

    audit_response = await client.get(
        "/admin/audit",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"range": "7d", "page": 1},
    )
    assert audit_response.status_code == 200
    assert audit_response.json()["total"] >= 2


@pytest.mark.asyncio
async def test_monitoring_llm_endpoint_returns_grouped_usage(client: AsyncClient) -> None:
    access_token = await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO llm_request_logs (
                    id,
                    request_kind,
                    actor_user_id,
                    task_id,
                    project_id,
                    agent_key,
                    provider_config_id,
                    provider_kind,
                    model,
                    status,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost_usd,
                    error_message,
                    created_at
                ) VALUES (
                    :id,
                    :request_kind,
                    NULL,
                    NULL,
                    NULL,
                    :agent_key,
                    NULL,
                    :provider_kind,
                    :model,
                    :status,
                    :latency_ms,
                    :prompt_tokens,
                    :completion_tokens,
                    :total_tokens,
                    :estimated_cost_usd,
                    NULL,
                    :created_at
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "request_kind": "chat",
                "agent_key": "qa",
                "provider_kind": "openrouter",
                "model": "openai/gpt-4o-mini",
                "status": "success",
                "latency_ms": 42,
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.001,
                "created_at": datetime.now(UTC),
            },
        )

    response = await client.get(
        "/admin/monitoring/llm",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"range": "7d"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["requests_total"] == 1
    assert payload["success_total"] == 1
    assert payload["error_total"] == 0
    assert payload["provider_breakdown"] == [{"provider_kind": "openrouter", "request_count": 1}]
    assert len(payload["daily"]) == 1
    assert payload["daily"][0]["total"] == 1
    assert payload["daily"][0]["providers"] == {"openrouter": 1}


@pytest.mark.asyncio
async def test_admin_can_update_llm_monitoring_mode(client: AsyncClient) -> None:
    access_token = await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )
    headers = {"Authorization": f"Bearer {access_token}"}

    get_response = await client.get("/admin/llm/runtime/settings", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["prompt_log_mode"] == "full"

    patch_response = await client.patch(
        "/admin/llm/runtime/settings",
        headers=headers,
        json={"prompt_log_mode": "disabled"},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["prompt_log_mode"] == "disabled"


@pytest.mark.asyncio
async def test_monitoring_llm_requests_endpoint_returns_prompt_and_response(
    client: AsyncClient,
) -> None:
    access_token = await register_and_login(
        client,
        email="admin@example.com",
        full_name="Admin User",
    )
    request_messages = [
        {"role": "system", "content": "Проверь требование."},
        {"role": "human", "content": "Нужно добавить аудит."},
    ]

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO llm_request_logs (
                    id,
                    request_kind,
                    actor_user_id,
                    task_id,
                    project_id,
                    agent_key,
                    provider_config_id,
                    provider_kind,
                    model,
                    status,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    estimated_cost_usd,
                    request_messages,
                    response_text,
                    error_message,
                    created_at
                ) VALUES (
                    :id,
                    :request_kind,
                    NULL,
                    NULL,
                    NULL,
                    :agent_key,
                    NULL,
                    :provider_kind,
                    :model,
                    :status,
                    :latency_ms,
                    :prompt_tokens,
                    :completion_tokens,
                    :total_tokens,
                    :estimated_cost_usd,
                    CAST(:request_messages AS JSONB),
                    :response_text,
                    NULL,
                    :created_at
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "request_kind": "chat",
                "agent_key": "task-validation",
                "provider_kind": "openai",
                "model": "gpt-4o-mini",
                "status": "success",
                "latency_ms": 120,
                "prompt_tokens": 20,
                "completion_tokens": 8,
                "total_tokens": 28,
                "estimated_cost_usd": 0.002,
                "request_messages": json.dumps(request_messages, ensure_ascii=False),
                "response_text": "Ответ модели",
                "created_at": datetime.now(UTC),
            },
        )

    response = await client.get(
        "/admin/monitoring/llm/requests",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"range": "7d", "page": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["prompt_log_mode"] == "full"
    assert payload["total"] == 1
    assert payload["items"][0]["request_messages"] == request_messages
    assert payload["items"][0]["response_text"] == "Ответ модели"


@pytest.mark.asyncio
async def test_admin_can_list_and_delete_validation_questions(client: AsyncClient) -> None:
    admin_token = await register_and_login(
        client,
        email="admin-validation@example.com",
        full_name="Admin User",
    )
    analyst_token = await register_and_login(
        client,
        email="analyst-validation@example.com",
        full_name="Analyst User",
    )

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    analyst_headers = {"Authorization": f"Bearer {analyst_token}"}

    users_response = await client.get("/users", headers=admin_headers)
    assert users_response.status_code == 200
    analyst_id = next(
        user["id"]
        for user in users_response.json()
        if user["email"] == "analyst-validation@example.com"
    )

    role_response = await client.patch(
        f"/users/{analyst_id}",
        headers=admin_headers,
        json={"role": "ANALYST"},
    )
    assert role_response.status_code == 200

    project_response = await client.post(
        "/projects",
        headers=analyst_headers,
        json={"name": "Validation backlog", "description": "Questions registry"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    task_response = await client.post(
        f"/projects/{project_id}/tasks",
        headers=analyst_headers,
        json={
            "title": "UI",
            "content": "Коротко.",
            "tags": [],
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    validate_response = await client.post(
        f"/tasks/{task_id}/validate",
        headers=analyst_headers,
    )
    assert validate_response.status_code == 200
    created_questions = validate_response.json()["questions"]
    assert created_questions

    list_response = await client.get(
        "/admin/validation/questions",
        headers=admin_headers,
        params={"task_status": "needs_rework"},
    )
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["total"] >= 1

    created_item = next(item for item in payload["items"] if item["task_id"] == task_id)
    assert created_item["question_text"] in created_questions
    assert created_item["project_id"] == project_id

    delete_response = await client.delete(
        f"/admin/validation/questions/{created_item['id']}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 204

    task_after_delete_response = await client.get(
        f"/projects/{project_id}/tasks/{task_id}",
        headers=analyst_headers,
    )
    assert task_after_delete_response.status_code == 200
    assert (
        created_item["question_text"]
        not in task_after_delete_response.json()["validation_result"]["questions"]
    )
