from __future__ import annotations

import asyncio
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.change_proposal import ChangeProposal
from app.models.graph_run_log import GraphRunLog
from app.models.message import Message
from app.models.orchestrator_eval import OrchestratorEvalCaseResult
from app.models.validation_question import ValidationQuestion


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


async def create_project(client: AsyncClient, token: str, *, name: str) -> str:
    response = await client.post(
        "/projects",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "description": "Eval project"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def import_payload(project_id: str) -> dict[str, Any]:
    return {
        "format": "json",
        "payload": {
            "dataset_name": "Orchestrator eval set",
            "project_id": project_id,
            "cases": [
                {
                    "external_id": "route-qa-pass",
                    "input": {
                        "project_id": project_id,
                        "task_id": None,
                        "task_title": "Авторизация",
                        "task_status": "draft",
                        "task_content": "Описание с корректной русской кодировкой.",
                        "validation_result": None,
                        "message_content": "@qa Какие требования к авторизации?",
                        "requested_agent": None,
                    },
                    "expected_route": {
                        "ai_response_required": True,
                        "target_agent_key": "qa",
                        "message_type": "general",
                        "routing_mode": "forced",
                        "reason_contains": "forced_agent",
                    },
                },
                {
                    "external_id": "route-qa-fail",
                    "input": {
                        "project_id": project_id,
                        "task_id": None,
                        "task_title": "Авторизация",
                        "task_status": "draft",
                        "task_content": "Описание с корректной русской кодировкой.",
                        "validation_result": None,
                        "message_content": "@qa Какие требования к авторизации?",
                        "requested_agent": None,
                    },
                    "expected_route": {
                        "ai_response_required": True,
                        "target_agent_key": "change-tracker",
                        "message_type": "change_proposal",
                        "routing_mode": "forced",
                    },
                },
            ],
        },
    }


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_run_orchestrator_eval_without_business_artifacts(
    client: AsyncClient,
) -> None:
    token = await register_and_login(
        client,
        email="orchestrator-eval@example.com",
        full_name="Orchestrator Eval Admin",
    )
    project_id = await create_project(client, token, name="Orchestrator Eval")
    headers = {"Authorization": f"Bearer {token}"}

    playground_response = await client.post(
        "/admin/orchestrator-eval/playground/run",
        headers=headers,
        json={
            "input": {
                "project_id": project_id,
                "task_id": None,
                "task_title": "Авторизация",
                "task_status": "draft",
                "task_content": "Описание с корректной русской кодировкой.",
                "validation_result": None,
                "message_content": "@qa Какие требования к авторизации?",
                "requested_agent": None,
            },
            "expected_route": {
                "ai_response_required": True,
                "target_agent_key": "qa",
                "message_type": "general",
                "routing_mode": "forced",
                "reason_contains": "forced_agent",
            },
            "config": {"compare_reason": True},
        },
    )
    assert playground_response.status_code == 200
    playground_payload = playground_response.json()
    assert playground_payload["status"] == "passed"
    assert playground_payload["actual_route"]["target_agent_key"] == "qa"
    assert playground_payload["graph_run_id"]

    async with AsyncSessionLocal() as db:
        trace = await db.get(GraphRunLog, playground_payload["graph_run_id"])
        messages_total = await db.scalar(select(func.count()).select_from(Message))
        proposals_total = await db.scalar(select(func.count()).select_from(ChangeProposal))
        questions_total = await db.scalar(
            select(func.count()).select_from(ValidationQuestion)
        )
    assert trace is not None
    assert trace.graph_key == "chat_routing_eval_graph"
    assert messages_total == 0
    assert proposals_total == 0
    assert questions_total == 0

    import_response = await client.post(
        "/admin/orchestrator-eval/datasets/import",
        headers=headers,
        json=import_payload(project_id),
    )
    assert import_response.status_code == 201
    import_result = import_response.json()
    assert import_result["imported_cases"] == 2
    assert "русской кодировкой" in import_result["dataset"]["cases"][0]["input"]["task_content"]
    dataset_id = import_result["dataset"]["id"]

    run_response = await client.post(
        f"/admin/orchestrator-eval/datasets/{dataset_id}/runs",
        headers=headers,
        json={"compare_reason": True},
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    detail = None
    for _ in range(10):
        detail_response = await client.get(
            f"/admin/orchestrator-eval/runs/{run_id}",
            headers=headers,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "success":
            break
        await asyncio.sleep(0.1)

    assert detail is not None
    assert detail["status"] == "success"
    assert detail["summary_metrics"]["total"] == 2
    assert detail["summary_metrics"]["passed"] == 1
    assert detail["summary_metrics"]["failed"] == 1
    statuses = {item["case_external_id"]: item["status"] for item in detail["case_results"]}
    assert statuses == {"route-qa-pass": "passed", "route-qa-fail": "failed"}

    history_response = await client.get(
        f"/admin/orchestrator-eval/datasets/{dataset_id}/runs",
        headers=headers,
    )
    assert history_response.status_code == 200
    assert history_response.json()["items"][0]["id"] == run_id

    csv_export = await client.get(
        f"/admin/orchestrator-eval/runs/{run_id}/export?format=csv",
        headers=headers,
    )
    assert csv_export.status_code == 200
    assert "case_external_id" in csv_export.text
    assert "route-qa-pass" in csv_export.text

    delete_response = await client.delete(
        f"/admin/orchestrator-eval/runs/{run_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204
    async with AsyncSessionLocal() as db:
        remaining_results = await db.scalar(
            select(func.count())
            .select_from(OrchestratorEvalCaseResult)
            .where(OrchestratorEvalCaseResult.run_id == run_id)
        )
    assert remaining_results == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_import_orchestrator_eval_csv_with_cyrillic(
    client: AsyncClient,
) -> None:
    token = await register_and_login(
        client,
        email="orchestrator-eval-csv@example.com",
        full_name="Orchestrator CSV Admin",
    )
    project_id = await create_project(client, token, name="Orchestrator CSV")
    csv_content = (
        "case_external_id,task_title,task_status,task_content,message_content,"
        "requested_agent,expected_ai_response_required,expected_target_agent_key,"
        "expected_message_type,expected_routing_mode,expected_reason_contains\n"
        "csv-1,Авторизация,draft,Русский текст сохранён,@qa Что уточнить?,,"
        "true,qa,general,forced,forced_agent\n"
    )

    response = await client.post(
        "/admin/orchestrator-eval/datasets/import",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "format": "csv",
            "dataset_name": "CSV routes",
            "project_id": project_id,
            "content": csv_content,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["dataset"]["cases_total"] == 1
    assert payload["dataset"]["cases"][0]["input"]["task_content"] == "Русский текст сохранён"
