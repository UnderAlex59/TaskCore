from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.database import AsyncSessionLocal
from app.models.graph_run_log import GraphRunLog
from app.models.message import Message
from app.models.task import Task
from app.models.validation_eval import ValidationEvalCaseResult
from app.models.validation_question import ValidationQuestion
from app.services.admin_validation_eval_service import AdminValidationEvalService


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
        json={"name": name, "description": "Validation Eval project"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def import_payload(project_id: str) -> dict[str, Any]:
    return {
        "format": "json",
        "payload": {
            "dataset_name": "Validation eval set",
            "project_id": project_id,
            "cases": [
                {
                    "external_id": "approved-with-question",
                    "title": "Авторизация пользователей",
                    "content": "Описание задачи с корректной русской кодировкой и критериями.",
                    "tags": ["auth"],
                    "attachment_names": ["mockup.png"],
                    "custom_rules": [
                        {
                            "title": "Безопасность",
                            "description": "Нужно указать требования безопасности.",
                            "applies_to_tags": ["auth"],
                        }
                    ],
                    "related_tasks": [{"task_id": "rel-1", "title": "SSO"}],
                    "historical_questions": ["Нужно ли приложить макет экрана входа?"],
                    "expected_verdict": "needs_rework",
                    "expected_issues": [
                        {
                            "code": "context_question",
                            "severity": "medium",
                            "message": "Нужно ли приложить макет экрана входа?",
                            "source": "context_questions",
                        }
                    ],
                    "expected_questions": [],
                    "expected_context_questions": [
                        "Нужно ли приложить макет экрана входа?"
                    ],
                    "metadata": {"source": "ручная разметка"},
                },
                {
                    "external_id": "needs-rework-core",
                    "title": "Оплата",
                    "content": "Сделать оплату быстро.",
                    "tags": ["billing"],
                    "attachment_names": [],
                    "custom_rules": [],
                    "related_tasks": [],
                    "historical_questions": [],
                    "expected_verdict": "needs_rework",
                    "expected_issues": [
                        {
                            "code": "ambiguous_language",
                            "severity": "high",
                            "message": "Обнаружены расплывчатые формулировки.",
                            "source": "core",
                        }
                    ],
                    "expected_questions": [],
                    "expected_context_questions": [],
                    "metadata": {"source": "регрессия"},
                },
            ],
        },
    }


def test_validation_eval_case_metrics_detects_issue_and_question_errors() -> None:
    metrics, diffs = AdminValidationEvalService._case_metrics(
        expected={
            "verdict": "needs_rework",
            "issues": [
                {
                    "code": "custom_rule_security",
                    "severity": "high",
                    "message": "Нет требований безопасности.",
                    "source": "custom_rule",
                }
            ],
            "questions": ["Какой SLA нужен?"],
            "context_questions": ["Какой макет нужен?"],
        },
        actual={
            "verdict": "approved",
            "issues": [
                {
                    "code": "extra_issue",
                    "severity": "medium",
                    "message": "Лишняя проблема.",
                }
            ],
            "questions": ["Какой SLA нужен?", "Какой SLA нужен?", "Кто пользователь?"],
            "context_questions": [
                "Какой макет нужен?",
                "Какой макет нужен?",
                "Какой исторический контекст важен?",
            ],
            "llm_diagnostics": [{"used_fallback": True, "parse_error": "invalid_json"}],
        },
    )

    assert metrics["verdict_match"] is False
    assert metrics["issue_precision"] == 0
    assert metrics["issue_recall"] == 0
    assert metrics["custom_rule_coverage"] == 0
    assert metrics["question_tp"] == 1
    assert metrics["question_fp"] == 2
    assert metrics["question_duplicates"] == 1
    assert metrics["context_question_tp"] == 1
    assert metrics["context_question_fp"] == 2
    assert metrics["context_question_duplicates"] == 1
    assert metrics["overall_question_tp"] == 2
    assert metrics["overall_question_fp"] == 4
    assert metrics["context_issue_fn"] == 0
    assert metrics["json_errors"] == 1
    assert diffs["false_negative_issues"][0]["code"] == "custom_rule_security"
    assert diffs["extra_context_questions"] == [
        "Какой макет нужен?",
        "Какой исторический контекст важен?",
    ]


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_manage_and_run_validation_eval(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await register_and_login(
        client,
        email="validation-eval@example.com",
        full_name="Validation Eval Admin",
    )
    project_id = await create_project(client, token, name="Validation Eval")
    headers = {"Authorization": f"Bearer {token}"}

    import_response = await client.post(
        "/admin/validation-eval/datasets/import",
        headers=headers,
        json=import_payload(project_id),
    )
    assert import_response.status_code == 201
    import_result = import_response.json()
    assert import_result["imported_cases"] == 2
    assert "русской кодировкой" in import_result["dataset"]["cases"][0]["content"]
    assert import_result["dataset"]["cases"][0]["expected_context_questions"] == [
        "Нужно ли приложить макет экрана входа?"
    ]
    dataset_id = import_result["dataset"]["id"]

    create_case_response = await client.post(
        f"/admin/validation-eval/datasets/{dataset_id}/cases",
        headers=headers,
        json={
            "external_id": "manual-case",
            "title": "Ручной кейс",
            "content": "Полное описание ручного кейса.",
            "tags": [],
            "attachment_names": [],
            "custom_rules": [],
            "related_tasks": [],
            "historical_questions": [],
            "expected_verdict": "approved",
            "expected_issues": [],
            "expected_questions": [],
            "expected_context_questions": [],
            "metadata": {},
        },
    )
    assert create_case_response.status_code == 201
    manual_case_id = create_case_response.json()["id"]

    patch_case_response = await client.patch(
        f"/admin/validation-eval/datasets/{dataset_id}/cases/{manual_case_id}",
        headers=headers,
        json={"title": "Ручной кейс обновлён"},
    )
    assert patch_case_response.status_code == 200
    assert patch_case_response.json()["title"] == "Ручной кейс обновлён"

    delete_case_response = await client.delete(
        f"/admin/validation-eval/datasets/{dataset_id}/cases/{manual_case_id}",
        headers=headers,
    )
    assert delete_case_response.status_code == 204

    async def fake_validation_eval_graph(**kwargs):  # type: ignore[no-untyped-def]
        db = kwargs["db"]
        graph_run = GraphRunLog(
            graph_key="validation_graph",
            status="success",
            actor_user_id=kwargs["actor_user_id"],
            project_id=kwargs["project_id"],
            source="validation_eval",
            finished_at=datetime.now(UTC),
            final_state_preview={"stub": True},
        )
        db.add(graph_run)
        await db.flush()
        if kwargs["title"] == "Оплата":
            return {
                "verdict": "needs_rework",
                "issues": [
                    {
                        "code": "ambiguous_language",
                        "severity": "high",
                        "message": "Обнаружены расплывчатые формулировки.",
                    }
                ],
                "questions": [],
                "graph_run_id": graph_run.id,
                "llm_diagnostics": [{"prompt_key": "task-validation-core", "ok": True}],
                "core_issues": [],
                "core_questions": [],
                "custom_rule_issues": [],
                "context_questions": [],
                "rag_questions": [],
            }
        questions = (
            ["Нужно ли приложить макет экрана входа?"]
            if kwargs["validation_node_settings"].get("context_questions")
            else []
        )
        issues = [
            {
                "finding_id": "context-finding-1",
                "source": "context_questions",
                "code": "context_question",
                "severity": "medium",
                "message": question,
            }
            for question in questions
        ]
        return {
            "verdict": "needs_rework" if issues else "approved",
            "issues": issues,
            "questions": [],
            "graph_run_id": graph_run.id,
            "llm_diagnostics": [{"prompt_key": "task-validation-core", "ok": True}],
            "core_issues": [],
            "core_questions": [],
            "custom_rule_issues": [],
            "context_questions": questions,
            "rag_questions": kwargs.get("historical_questions", []),
        }

    async def fake_question_judge(**kwargs):  # type: ignore[no-untyped-def]
        db = kwargs["db"]
        graph_run = GraphRunLog(
            graph_key="validation_eval_question_judge_graph",
            status="success",
            actor_user_id=kwargs["actor_user_id"],
            project_id=kwargs["project_id"],
            source="validation_eval",
            finished_at=datetime.now(UTC),
            final_state_preview={"stub": True},
        )
        db.add(graph_run)
        await db.flush()
        return {
            "judge_payload": {
                "relevance": 1.0,
                "specificity": 0.9,
                "actionability": 0.8,
                "novelty": 0.7,
                "ok": True,
            },
            "judge_graph_run_id": graph_run.id,
        }

    monkeypatch.setattr(
        "app.services.admin_validation_eval_service.run_validation_eval_graph",
        fake_validation_eval_graph,
    )
    monkeypatch.setattr(
        "app.services.admin_validation_eval_service.run_validation_eval_question_judge_graph",
        fake_question_judge,
    )

    run_response = await client.post(
        f"/admin/validation-eval/datasets/{dataset_id}/runs",
        headers=headers,
        json={},
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    detail = None
    for _ in range(10):
        detail_response = await client.get(
            f"/admin/validation-eval/runs/{run_id}",
            headers=headers,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "success":
            break
        await asyncio.sleep(0.1)

    assert detail is not None
    assert detail["status"] == "success"
    assert len(detail["case_results"]) == 6
    assert detail["summary_metrics"]["variants"]["full"]["cases_total"] == 2
    assert detail["summary_metrics"]["variants"]["full"]["verdict_accuracy"] == 1
    assert detail["summary_metrics"]["variants"]["full"]["context_question_f1"] == 1
    assert detail["summary_metrics"]["variants"]["full"]["overall_question_f1"] == 1
    assert detail["summary_metrics"]["variants"]["full"]["context_issue_f1"] == 1
    assert detail["summary_metrics"]["variants"]["full"]["context_question_judge"][
        "relevance"
    ] == 1
    assert detail["summary_metrics"]["ablation"]
    assert "context_question_f1_delta" in detail["summary_metrics"]["ablation"][0]
    assert all(item["graph_run_id"] for item in detail["case_results"])
    assert any(item["judge_graph_run_id"] for item in detail["case_results"])

    async with AsyncSessionLocal() as db:
        tasks_total = await db.scalar(select(func.count()).select_from(Task))
        messages_total = await db.scalar(select(func.count()).select_from(Message))
        questions_total = await db.scalar(select(func.count()).select_from(ValidationQuestion))
    assert tasks_total == 0
    assert messages_total == 0
    assert questions_total == 0

    history_response = await client.get(
        f"/admin/validation-eval/datasets/{dataset_id}/runs",
        headers=headers,
    )
    assert history_response.status_code == 200
    assert history_response.json()["items"][0]["id"] == run_id

    for artifact in ("case_results", "metrics", "confusion_matrix", "ablation", "errors"):
        csv_response = await client.get(
            f"/admin/validation-eval/runs/{run_id}/export",
            headers=headers,
            params={"artifact": artifact, "format": "csv"},
        )
        assert csv_response.status_code == 200
        assert csv_response.text
        if artifact == "case_results":
            assert "context_question_f1" in csv_response.text
            assert "overall_question_f1" in csv_response.text
        if artifact == "ablation":
            assert "context_question_f1_delta" in csv_response.text
            assert "overall_question_f1_delta" in csv_response.text
        json_response = await client.get(
            f"/admin/validation-eval/runs/{run_id}/export",
            headers=headers,
            params={"artifact": artifact, "format": "json"},
        )
        assert json_response.status_code == 200
        if artifact == "errors":
            assert any(
                row["error_type"] in {"extra_context_question", "missing_context_question"}
                for row in json_response.json()
            )

    delete_run_response = await client.delete(
        f"/admin/validation-eval/runs/{run_id}",
        headers=headers,
    )
    assert delete_run_response.status_code == 204
    async with AsyncSessionLocal() as db:
        remaining_results = await db.scalar(
            select(func.count())
            .select_from(ValidationEvalCaseResult)
            .where(ValidationEvalCaseResult.run_id == run_id)
        )
    assert remaining_results == 0

    delete_dataset_response = await client.delete(
        f"/admin/validation-eval/datasets/{dataset_id}",
        headers=headers,
    )
    assert delete_dataset_response.status_code == 204


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_validation_eval_rejects_duplicate_cases_invalid_variants_and_active_delete(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await register_and_login(
        client,
        email="validation-eval-invalid@example.com",
        full_name="Validation Eval Invalid Admin",
    )
    project_id = await create_project(client, token, name="Validation Eval Invalid")
    headers = {"Authorization": f"Bearer {token}"}

    duplicate_payload = import_payload(project_id)
    duplicate_payload["payload"]["cases"][1]["external_id"] = "approved-with-question"
    duplicate_response = await client.post(
        "/admin/validation-eval/datasets/import",
        headers=headers,
        json=duplicate_payload,
    )
    assert duplicate_response.status_code == 422

    import_response = await client.post(
        "/admin/validation-eval/datasets/import",
        headers=headers,
        json=import_payload(project_id),
    )
    assert import_response.status_code == 201
    dataset_id = import_response.json()["dataset"]["id"]

    invalid_provider_response = await client.post(
        f"/admin/validation-eval/datasets/{dataset_id}/runs",
        headers=headers,
        json={
            "variants": [
                {
                    "key": "bad-provider",
                    "validation_node_settings": {"core_rules": True},
                    "provider_config_id": "00000000-0000-0000-0000-000000000000",
                    "prompt_version_ids": {},
                }
            ],
            "run_question_judge": False,
        },
    )
    assert invalid_provider_response.status_code == 422

    async def noop_process_run(run_id: str) -> None:
        return None

    monkeypatch.setattr(
        "app.routers.admin.AdminValidationEvalService.process_run",
        noop_process_run,
    )
    run_response = await client.post(
        f"/admin/validation-eval/datasets/{dataset_id}/runs",
        headers=headers,
        json={"run_question_judge": False},
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    active_delete_response = await client.delete(
        f"/admin/validation-eval/runs/{run_id}",
        headers=headers,
    )
    assert active_delete_response.status_code == 409
