from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import AsyncClient
from langchain_core.documents import Document
from sqlalchemy import func, select

from app.agents.adaptation_eval_match_judge_graph import (
    run_adaptation_eval_match_judge_graph,
)
from app.core.database import AsyncSessionLocal
from app.models.task import Task
from app.models.validation_question import ValidationQuestion
from app.services.admin_adaptation_eval_service import AdminAdaptationEvalService
from app.services.llm_runtime_service import LLMInvocationResult
from app.services.validation_question_service import ValidationQuestionService


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
        json={"name": name, "description": "Adaptation Eval project"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def import_payload(project_id: str) -> dict[str, Any]:
    return {
        "dataset_name": "Adaptation eval set",
        "project_id": project_id,
        "cases": [
            {
                "external_id": "adapt-auth-positive",
                "scenario_type": "positive",
                "historical_tasks": [
                    {
                        "title": "Авторизация",
                        "content": "Нужно описать вход по email.",
                        "tags": ["auth"],
                        "chat_messages": [
                            "Какие роли пользователей должны поддерживаться?"
                        ],
                    }
                ],
                "probe_task": {
                    "title": "Вход в кабинет",
                    "content": "Нужно реализовать вход по email и паролю.",
                    "tags": ["auth"],
                    "custom_rules": [],
                    "related_tasks": [],
                    "attachment_names": [],
                },
                "expected_captured_questions": [
                    "Какие роли пользователей должны поддерживаться?"
                ],
                "expected_retrieved_questions": [
                    "Какие роли пользователей должны поддерживаться?"
                ],
                "expected_context_questions": [
                    "Какие роли пользователей должны поддерживаться?"
                ],
                "expected_verdict": "needs_rework",
                "expected_context_issues": [
                    {
                        "code": "context_question",
                        "severity": "medium",
                        "message": "Какие роли пользователей должны поддерживаться?",
                        "source": "context_questions",
                    }
                ],
                "metadata": {"scenario": "positive"},
            }
        ],
    }


def test_adaptation_eval_case_metrics_cover_chain() -> None:
    metrics, diffs = AdminAdaptationEvalService._case_metrics(
        expected={
            "captured_questions": ["Какие роли нужны?"],
            "retrieved_questions": ["Какие роли нужны?"],
            "context_questions": ["Какие роли нужны?"],
            "verdict": "needs_rework",
            "context_issues": [
                {
                    "code": "context_question",
                    "message": "Какие роли нужны?",
                    "source": "context_questions",
                }
            ],
        },
        actual={
            "captured_questions": ["Какие роли нужны?", "Какие роли нужны?"],
            "retrieved_questions": ["Какие роли нужны?"],
            "context_validation": {
                "verdict": "needs_rework",
                "issues": [
                    {
                        "code": "context_question",
                        "message": "Какие роли нужны?",
                        "source": "context_questions",
                    }
                ],
                "context_questions": ["Какие роли нужны?"],
            },
        },
    )

    assert metrics["capture_recall"] == 1
    assert metrics["retrieval_recall_at_k"] == 1
    assert metrics["context_question_f1"] == 1
    assert metrics["context_issue_f1"] == 1
    assert "full_vs_core_custom_context_question_f1_delta" not in metrics
    assert "full_vs_core_custom_context_issue_f1_delta" not in metrics
    assert "core_context_question_f1" not in metrics
    assert "core_context_issue_f1" not in metrics
    assert metrics["overall_question_duplicate_rate"] > 0
    assert diffs["capture_matches"][0]["expected"] == "Какие роли нужны?"


def test_adaptation_eval_metrics_cover_partial_negative_and_missing() -> None:
    metrics, diffs = AdminAdaptationEvalService._case_metrics(
        expected={
            "captured_questions": ["Есть ли SLA эскалации инцидента?"],
            "retrieved_questions": ["Есть ли SLA эскалации инцидента?"],
            "context_questions": [],
            "verdict": "approved",
            "context_issues": [],
        },
        actual={
            "captured_questions": ["Уточнить, есть ли SLA эскалации инцидента"],
            "retrieved_questions": [],
            "context_validation": {
                "verdict": "approved",
                "issues": [],
                "context_questions": [],
            },
        },
    )

    assert metrics["capture_f1"] == 1
    assert metrics["retrieval_recall_at_k"] == 0
    assert metrics["context_question_f1"] == 1
    assert metrics["context_issue_f1"] == 1
    assert metrics["passed"] is False
    assert diffs["missing_retrievals"] == ["Есть ли SLA эскалации инцидента?"]


def test_adaptation_eval_metrics_accept_judge_paraphrase() -> None:
    metrics, diffs = AdminAdaptationEvalService._case_metrics(
        expected={
            "captured_questions": [
                "Какой SLA обработки критического инцидента считается допустимым?"
            ],
            "retrieved_questions": [],
            "context_questions": [],
            "verdict": "approved",
            "context_issues": [],
        },
        actual={
            "captured_questions": [
                "Какое значение SLA установлено для обработки критических инцидентов?"
            ],
            "retrieved_questions": [],
            "context_validation": {
                "verdict": "approved",
                "issues": [],
                "context_questions": [],
            },
        },
        judge_payloads={
            "capture": {
                "judge_payload": {
                    "ok": True,
                    "matches": [
                        {
                            "expected_index": 0,
                            "actual_index": 0,
                            "match": True,
                            "confidence": 0.92,
                            "reason": "Оба вопроса про допустимое значение SLA инцидента.",
                        }
                    ],
                },
                "judge_graph_run_id": "judge-run-1",
            }
        },
        judge_match_confidence_min=0.75,
    )

    assert metrics["capture_f1"] == 1
    assert metrics["capture_text_f1"] == 0
    assert metrics["judge_match_rate"] == 1
    assert diffs["capture_matches"][0]["match_source"] == "judge"
    assert diffs["capture_judge_graph_run_id"] == "judge-run-1"


@pytest.mark.asyncio
async def test_adaptation_eval_exact_match_skips_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_judge(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Judge must not run for deterministic matches")

    monkeypatch.setattr(
        "app.services.admin_adaptation_eval_service.run_adaptation_eval_match_judge_graph",
        fail_judge,
    )

    payloads = await AdminAdaptationEvalService._case_judge_payloads(
        case=SimpleNamespace(
            external_id="exact-case",
            scenario_type="positive",
            probe_task={"title": "Auth", "content": "Auth task"},
        ),
        project_id="project-1",
        expected={
            "captured_questions": ["Какие роли пользователей нужны?"],
            "retrieved_questions": ["Какие роли пользователей нужны?"],
            "context_questions": ["Какие роли пользователей нужны?"],
            "verdict": "needs_rework",
            "context_issues": [
                {
                    "code": "context_question",
                    "message": "Какие роли пользователей нужны?",
                    "source": "context_questions",
                }
            ],
        },
        actual={
            "captured_questions": ["Какие роли пользователей нужны?"],
            "retrieved_questions": ["Какие роли пользователей нужны?"],
            "context_validation": {
                "verdict": "needs_rework",
                "issues": [
                    {
                        "code": "context_question",
                        "message": "Какие роли пользователей нужны?",
                        "source": "context_questions",
                    }
                ],
                "context_questions": ["Какие роли пользователей нужны?"],
            },
        },
        config=SimpleNamespace(run_match_judge=True),
        actor=SimpleNamespace(id="user-1"),
        db=SimpleNamespace(),
    )

    assert payloads == {}


@pytest.mark.asyncio
async def test_adaptation_eval_match_judge_retries_invalid_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_temperatures: list[float | None] = []
    responses = iter(["not json", '{"matches":[{"expected_index":0,"actual_index":0,'
                          '"match":true,"confidence":0.88,"reason":"same"}],'
                          '"unmatched_expected_indices":[],"unmatched_actual_indices":[],'
                          '"ok":true}'])

    async def fake_invoke_chat(*args, **kwargs):  # type: ignore[no-untyped-def]
        seen_temperatures.append(kwargs.get("temperature_override"))
        return LLMInvocationResult(
            ok=True,
            text=next(responses),
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o-mini",
            latency_ms=10,
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )

    state = await run_adaptation_eval_match_judge_graph(
        db=SimpleNamespace(),
        actor_user_id="user-1",
        project_id="project-1",
        case_external_id="case-1",
        scenario_type="positive",
        group_key="capture",
        task_title="SLA",
        task_content="Task content",
        expected_items=[{"index": 0, "text": "Какой SLA нужен?"}],
        actual_items=[{"index": 0, "text": "Какое значение SLA требуется?"}],
    )

    payload = state["judge_payload"]
    assert seen_temperatures == [None, 0.0]
    assert payload["ok"] is True
    assert payload["invalid_json_count"] == 1
    assert payload["retry_count"] == 1
    assert payload["matches"][0]["confidence"] == 0.88


@pytest.mark.asyncio
async def test_adaptation_eval_validation_variant_uses_context_level_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_settings: list[dict[str, bool]] = []

    async def fake_validation_graph(**kwargs):  # type: ignore[no-untyped-def]
        seen_settings.append(dict(kwargs["validation_node_settings"]))
        return {
            "verdict": "approved",
            "issues": [],
            "questions": [],
            "context_questions": [],
            "rag_questions": [],
            "llm_diagnostics": [],
            "graph_run_id": None,
        }

    monkeypatch.setattr(
        "app.services.admin_adaptation_eval_service.run_validation_graph",
        fake_validation_graph,
    )

    result = await AdminAdaptationEvalService._run_validation_variant(
        db=SimpleNamespace(),
        actor=SimpleNamespace(id="user-1"),
        run=SimpleNamespace(project_id="project-1"),
        probe_task_id="task-1",
        probe_task={
            "title": "Проверка контекстного уровня",
            "content": "Описание задачи",
            "tags": ["auth"],
        },
    )
    assert result["validation_node_settings"] == {
        "core_rules": False,
        "custom_rules": False,
        "context_questions": True,
    }

    assert seen_settings == [
        {"core_rules": False, "custom_rules": False, "context_questions": True},
    ]


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_run_adaptation_eval(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await register_and_login(
        client,
        email="adaptation-eval@example.com",
        full_name="Adaptation Eval Admin",
    )
    project_id = await create_project(client, token, name="Adaptation Eval")
    headers = {"Authorization": f"Bearer {token}"}

    async def fake_process_pending_response(pending):  # type: ignore[no-untyped-def]
        async with AsyncSessionLocal() as db:
            task = await db.get(Task, pending.task_id)
            assert task is not None
            await ValidationQuestionService.record_chat_question(
                task,
                pending.routed_content,
                db,
                actor_user_id=pending.actor_user_id,
            )
            await db.commit()

    async def fake_probe_project_questions_with_scores(**kwargs):  # type: ignore[no-untyped-def]
        if "auth" not in kwargs["tags"]:
            return []
        return [
            {
                "document": Document(
                    page_content="Какие роли пользователей должны поддерживаться?",
                    metadata={
                        "question_id": "question-1",
                        "task_id": "historical-task-1",
                        "project_id": kwargs["project_id"],
                        "tags": ["auth"],
                    },
                ),
                "score": 0.96,
                "rank": 1,
            }
        ]

    seen_validation_settings: list[dict[str, bool]] = []

    async def fake_validation_graph(**kwargs):  # type: ignore[no-untyped-def]
        seen_validation_settings.append(dict(kwargs["validation_node_settings"]))
        if kwargs["validation_node_settings"].get("context_questions"):
            question = "Какие роли пользователей должны поддерживаться?"
            return {
                "verdict": "needs_rework",
                "issues": [
                    {
                        "code": "context_question",
                        "severity": "medium",
                        "message": question,
                        "source": "context_questions",
                    }
                ],
                "questions": [],
                "context_questions": [question],
                "rag_questions": [question],
                "llm_diagnostics": [],
                "graph_run_id": None,
            }
        return {
            "verdict": "approved",
            "issues": [],
            "questions": [],
            "context_questions": [],
            "rag_questions": [],
            "llm_diagnostics": [],
            "graph_run_id": None,
        }

    monkeypatch.setattr(
        "app.services.chat_service.ChatService.process_pending_response",
        fake_process_pending_response,
    )
    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.probe_project_questions_with_scores",
        fake_probe_project_questions_with_scores,
    )
    monkeypatch.setattr(
        "app.services.admin_adaptation_eval_service.run_validation_graph",
        fake_validation_graph,
    )

    import_response = await client.post(
        "/admin/adaptation-eval/datasets/import",
        headers=headers,
        json=import_payload(project_id),
    )
    assert import_response.status_code == 201
    imported = import_response.json()
    assert imported["imported_cases"] == 1
    dataset_id = imported["dataset"]["id"]

    run_response = await client.post(
        f"/admin/adaptation-eval/datasets/{dataset_id}/runs",
        headers=headers,
        json={"run_match_judge": False},
    )
    assert run_response.status_code == 201
    run_id = run_response.json()["id"]

    detail = None
    for _ in range(10):
        detail_response = await client.get(
            f"/admin/adaptation-eval/runs/{run_id}",
            headers=headers,
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "success":
            break
        await asyncio.sleep(0.1)

    assert detail is not None
    assert detail["status"] == "success"
    assert detail["summary_metrics"]["gate_status"] == "passed"
    assert detail["summary_metrics"]["capture_recall"] == 1
    assert detail["summary_metrics"]["retrieval_recall_at_k"] == 1
    assert detail["summary_metrics"]["context_question_f1"] == 1
    assert "full_vs_core_custom_context_question_f1_delta" not in detail[
        "summary_metrics"
    ]
    assert [gate["key"] for gate in detail["summary_metrics"]["quality_gates"]] == [
        "capture_recall",
        "retrieval_recall_at_k",
        "context_question_f1",
        "context_issue_f1",
        "overall_question_duplicate_rate",
    ]
    assert detail["case_results"][0]["status"] == "passed"
    assert detail["case_results"][0]["actual_result"]["captured_questions"] == [
        "Какие роли пользователей должны поддерживаться?"
    ]
    assert seen_validation_settings == [
        {"core_rules": False, "custom_rules": False, "context_questions": True}
    ]
    actual_result = detail["case_results"][0]["actual_result"]
    assert "core_custom_validation" not in actual_result
    assert "full_validation" not in actual_result
    assert actual_result["context_validation"]["validation_node_settings"] == {
        "core_rules": False,
        "custom_rules": False,
        "context_questions": True,
    }

    metrics_export = await client.get(
        f"/admin/adaptation-eval/runs/{run_id}/export",
        headers=headers,
        params={"artifact": "metrics", "format": "csv"},
    )
    assert metrics_export.status_code == 200
    assert "capture_recall" in metrics_export.text

    async with AsyncSessionLocal() as db:
        tasks_total = await db.scalar(select(func.count()).select_from(Task))
        questions_total = await db.scalar(
            select(func.count()).select_from(ValidationQuestion)
        )
    assert tasks_total == 0
    assert questions_total == 0
