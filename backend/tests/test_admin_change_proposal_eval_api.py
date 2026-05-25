from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient

from app.schemas.admin_change_proposal_eval import ChangeProposalEvalRunPayload
from app.services.admin_change_proposal_eval_service import AdminChangeProposalEvalService


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
        json={"name": name, "description": "Change proposal eval project"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def payload(project_id: str) -> dict[str, Any]:
    return {
        "project_id": project_id,
        "config": {
            "mode": "route_then_extract",
            "semantic_match_threshold": 0.55,
        },
        "cases": [
            {
                "external_id": "proposal-create",
                "task_title": "Импорт реестра документов",
                "task_status": "ready_for_dev",
                "task_content": "Система импортирует файл реестра документов.",
                "message_content": (
                    "Нужно добавить требование: если часть строк не прошла проверку, "
                    "пользователь должен скачать отчет с ошибками."
                ),
                "expected_is_proposal": True,
                "expected_proposal_text": (
                    "Добавить отчет с ошибками для строк файла, которые не прошли "
                    "проверку при импорте."
                ),
                "expected_duplicate": False,
                "expected_action": "create",
            },
            {
                "external_id": "proposal-ignore",
                "task_title": "Рассылка по статусам",
                "task_status": "draft",
                "task_content": "Система отправляет уведомления при изменении статуса.",
                "message_content": "А кто будет получать уведомления при изменении статуса?",
                "expected_is_proposal": False,
                "expected_proposal_text": None,
                "expected_duplicate": False,
                "expected_action": "ignore",
            },
            {
                "external_id": "proposal-duplicate",
                "task_title": "Импорт реестра документов",
                "task_status": "ready_for_dev",
                "task_content": "Система импортирует файл реестра документов.",
                "message_content": "Дубликат: давайте еще добавим файл с ошибками по строкам.",
                "expected_is_proposal": True,
                "expected_proposal_text": (
                    "Добавить отчет с ошибками для строк файла, которые не прошли "
                    "проверку при импорте."
                ),
                "expected_duplicate": True,
                "expected_duplicate_of": "proposal-create",
                "expected_action": "skip_duplicate",
            },
        ],
    }


def stub_eval_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import admin_change_proposal_eval_service as service_module

    async def fake_route(**kwargs: Any) -> dict[str, Any]:
        message = str(kwargs["message_content"])
        if message.startswith("А кто"):
            return {
                "actual_route": {
                    "ai_response_required": False,
                    "target_agent_key": None,
                    "message_type": "general",
                    "routing_mode": "auto",
                    "routing_reason": "ordinary_question",
                },
                "graph_run_id": "route-ignore",
            }
        return {
            "actual_route": {
                "ai_response_required": True,
                "target_agent_key": "change-tracker",
                "message_type": "change_proposal",
                "routing_mode": "auto",
                "routing_reason": "proposal_request",
            },
            "graph_run_id": "route-proposal",
        }

    async def fake_change_tracker(**kwargs: Any) -> dict[str, Any]:
        message = str(kwargs["message_content"])
        source_ref: dict[str, Any] = {
            "collection": "task_proposals",
            "agent_key": "change-tracker",
        }
        if message.startswith("Дубликат"):
            source_ref.update(
                {
                    "duplicate_proposal": True,
                    "duplicate_proposal_id": "existing-proposal",
                }
            )
        return {
            "message_type": "agent_proposal",
            "proposal_text": (
                "Добавить отчет с ошибками для строк файла, которые не прошли "
                "проверку при импорте."
            ),
            "source_ref": source_ref,
            "response": "Предложение зарегистрировано.",
            "graph_run_id": "change-run",
        }

    monkeypatch.setattr(service_module, "run_chat_routing_eval_graph", fake_route)
    monkeypatch.setattr(
        service_module,
        "run_change_tracker_agent_graph",
        fake_change_tracker,
    )


@pytest.mark.asyncio
async def test_change_proposal_eval_service_calculates_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_eval_agents(monkeypatch)

    result = await AdminChangeProposalEvalService.run(
        ChangeProposalEvalRunPayload.model_validate(payload("project-id")),
        SimpleNamespace(id="actor-id"),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
    )

    assert result.status == "success"
    assert result.summary_metrics["proposal_f1"] == 1
    assert result.summary_metrics["proposal_text_f1"] == 1
    assert result.summary_metrics["duplicate_f1"] == 1
    assert result.summary_metrics["structured_artifact_rate"] == 1
    assert {item.status for item in result.case_results} == {"passed"}


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_run_change_proposal_eval(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_eval_agents(monkeypatch)

    token = await register_and_login(
        client,
        email="change-proposal-eval@example.com",
        full_name="Change Proposal Eval Admin",
    )
    project_id = await create_project(client, token, name="Change Proposal Eval")

    response = await client.post(
        "/admin/change-proposal-eval/run",
        headers={"Authorization": f"Bearer {token}"},
        json=payload(project_id),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["summary_metrics"]["cases_total"] == 3
    assert body["summary_metrics"]["proposal_f1"] == 1
    assert body["summary_metrics"]["proposal_text_f1"] == 1
    assert body["summary_metrics"]["duplicate_f1"] == 1
    assert body["summary_metrics"]["false_creation_rate"] == 0
    assert {item["status"] for item in body["case_results"]} == {"passed"}
