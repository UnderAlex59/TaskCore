from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from app.models.graph_run_log import GraphRunLog
from app.services.admin_qure_eval_service import AdminQureEvalService, QureCsvRow


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
        json={"name": name, "description": "QuRE Eval project"},
    )
    assert response.status_code == 201
    return str(response.json()["id"])


def qure_csv() -> str:
    return "\n".join(
        [
            "id,requirement,defect,weak_word",
            "0,The system shall use adequate naming.,ok,adequate",
            "1,The system shall respond fast.,defect,fast",
            "2,The event shall happen soon.,defect,soon",
            "3,The service shall support a large number of users.,ok,large",
        ]
    )


def test_qure_parser_accepts_only_source_schema() -> None:
    rows = AdminQureEvalService.parse_qure_csv(qure_csv().encode("utf-8"))

    assert rows[0].source_id == "0"
    assert rows[0].expected_verdict == "approved"
    assert rows[1].expected_verdict == "needs_rework"

    with pytest.raises(HTTPException):
        AdminQureEvalService.parse_qure_csv(
            b"case_external_id,title,content,expected_verdict\n1,t,c,approved\n"
        )
    with pytest.raises(HTTPException):
        AdminQureEvalService.parse_qure_csv(
            b"id,requirement,defect,weak_word\n1,Requirement,maybe,weak\n"
        )
    with pytest.raises(HTTPException):
        AdminQureEvalService.parse_qure_csv(
            b"id,requirement,defect,weak_word\n1,Requirement,ok,weak\n1,Other,ok,weak\n"
        )


def test_qure_stratified_selection_is_reproducible_and_not_first_n() -> None:
    rows = [
        QureCsvRow(index, str(index), f"Requirement {index}", "ok", "adequate")
        for index in range(10)
    ]
    rows.extend(
        QureCsvRow(index, str(index), f"Requirement {index}", "defect", "fast")
        for index in range(10, 20)
    )

    first = AdminQureEvalService.select_stratified_rows(rows, 6)
    second = AdminQureEvalService.select_stratified_rows(rows, 6)

    assert [row.row_index for row in first] == [row.row_index for row in second]
    assert [row.row_index for row in first] != list(range(6))
    assert {row.defect for row in first} == {"ok", "defect"}


def test_qure_case_metrics_cover_verdict_and_weak_word() -> None:
    metrics = AdminQureEvalService._case_metrics(
        defect="defect",
        expected_verdict="needs_rework",
        actual_verdict="approved",
        judge_match=False,
    )

    assert metrics["verdict_fn"] == 1
    assert metrics["weak_word_fn"] == 1


class NoopDb:
    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_qure_run_case_status_comes_from_judge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_validation_eval_graph(**kwargs: Any) -> dict[str, Any]:
        return {
            "verdict": "needs_rework",
            "issues": [{"code": "ambiguous_language", "message": "Weak wording"}],
            "questions": [],
            "graph_run_id": "validation-run",
            "llm_diagnostics": [],
            "core_issues": [{"code": "ambiguous_language", "message": "Weak wording"}],
            "core_questions": [],
        }

    async def fake_failed_judge(**kwargs: Any) -> dict[str, Any]:
        return {
            "judge_payload": {
                "passed": False,
                "match": False,
                "score": 0.2,
                "verdict_match": True,
                "weak_word_match": False,
                "matched_issue_indices": [],
                "rationale": "Validator verdict matched but issue missed the weak word.",
                "ok": True,
            },
            "judge_graph_run_id": "judge-run",
        }

    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_validation_eval_graph",
        fake_validation_eval_graph,
    )
    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_qure_eval_weak_word_judge_graph",
        fake_failed_judge,
    )

    result = SimpleNamespace(
        defect="defect",
        expected_verdict="needs_rework",
        requirement="The system shall respond fast.",
        source_id="1",
        weak_word="fast",
    )

    await AdminQureEvalService._run_case(
        SimpleNamespace(created_by="user-1", project_id="project-1"),
        result,
        NoopDb(),  # type: ignore[arg-type]
    )

    assert result.status == "failed"
    assert result.metrics["verdict_match"] is True
    assert result.metrics["judge_passed"] is False
    assert result.metrics["result_source"] == "llm_judge"


@pytest.mark.asyncio
async def test_qure_run_case_calls_judge_for_empty_validator_issues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_actual_issues: list[list[dict[str, Any]]] = []

    async def fake_validation_eval_graph(**kwargs: Any) -> dict[str, Any]:
        return {
            "verdict": "approved",
            "issues": [],
            "questions": [],
            "graph_run_id": "validation-run",
            "llm_diagnostics": [],
            "core_issues": [],
            "core_questions": [],
        }

    async def fake_passed_judge(**kwargs: Any) -> dict[str, Any]:
        seen_actual_issues.append(list(kwargs["actual_issues"]))
        return {
            "judge_payload": {
                "passed": True,
                "match": True,
                "score": 1.0,
                "verdict_match": True,
                "weak_word_match": False,
                "matched_issue_indices": [],
                "rationale": "Validator correctly approved the ok case.",
                "ok": True,
            },
            "judge_graph_run_id": "judge-run",
        }

    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_validation_eval_graph",
        fake_validation_eval_graph,
    )
    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_qure_eval_weak_word_judge_graph",
        fake_passed_judge,
    )

    result = SimpleNamespace(
        defect="ok",
        expected_verdict="approved",
        requirement="The system shall use adequate naming.",
        source_id="0",
        weak_word="adequate",
    )

    await AdminQureEvalService._run_case(
        SimpleNamespace(created_by="user-1", project_id="project-1"),
        result,
        NoopDb(),  # type: ignore[arg-type]
    )

    assert seen_actual_issues == [[]]
    assert result.status == "passed"
    assert result.judge_graph_run_id == "judge-run"


@pytest.mark.asyncio
async def test_qure_run_case_marks_error_for_invalid_judge_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_validation_eval_graph(**kwargs: Any) -> dict[str, Any]:
        return {
            "verdict": "approved",
            "issues": [],
            "questions": [],
            "graph_run_id": "validation-run",
            "llm_diagnostics": [],
            "core_issues": [],
            "core_questions": [],
        }

    async def fake_invalid_judge(**kwargs: Any) -> dict[str, Any]:
        return {
            "judge_payload": {
                "ok": False,
                "rationale": "Judge did not return a valid QuRE decision.",
            },
            "judge_graph_run_id": "judge-run",
        }

    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_validation_eval_graph",
        fake_validation_eval_graph,
    )
    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_qure_eval_weak_word_judge_graph",
        fake_invalid_judge,
    )

    result = SimpleNamespace(
        defect="defect",
        expected_verdict="needs_rework",
        requirement="The system shall respond fast.",
        source_id="1",
        weak_word="fast",
    )

    await AdminQureEvalService._run_case(
        SimpleNamespace(created_by="user-1", project_id="project-1"),
        result,
        NoopDb(),  # type: ignore[arg-type]
    )

    assert result.status == "error"
    assert result.error_message == "Judge did not return a valid QuRE decision."
    assert result.metrics["judge_ok"] is False
    assert result.metrics["result_source"] == "llm_judge"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_admin_can_create_run_process_core_only_and_export(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await register_and_login(
        client,
        email="qure-eval@example.com",
        full_name="QuRE Eval Admin",
    )
    project_id = await create_project(client, token, name="QuRE Eval")
    headers = {"Authorization": f"Bearer {token}"}
    seen_settings: list[dict[str, bool]] = []
    seen_judge_issues: list[list[dict[str, Any]]] = []

    async def fake_validation_eval_graph(**kwargs: Any) -> dict[str, Any]:
        seen_settings.append(dict(kwargs["validation_node_settings"]))
        db = kwargs["db"]
        graph_run = GraphRunLog(
            graph_key="validation_graph",
            status="success",
            actor_user_id=kwargs["actor_user_id"],
            project_id=kwargs["project_id"],
            source="qure_eval",
            finished_at=datetime.now(UTC),
            final_state_preview={"stub": True},
        )
        db.add(graph_run)
        await db.flush()
        content = str(kwargs["content"])
        weak_word = str(kwargs["title"]).split(": ", 1)[-1]
        if weak_word == "adequate":
            issues: list[dict[str, str]] = []
            verdict = "approved"
        else:
            issues = [
                {
                    "code": "ambiguous_language",
                    "severity": "high",
                    "message": f"Potential weak wording: {weak_word}",
                }
            ]
            verdict = "needs_rework"
        return {
            "verdict": verdict,
            "issues": issues,
            "questions": [],
            "graph_run_id": graph_run.id,
            "llm_diagnostics": [{"prompt_key": "task-validation-core", "ok": True}],
            "core_issues": issues,
            "core_questions": [],
            "custom_rule_issues": [],
            "context_questions": [],
            "rag_questions": [],
            "echo": content,
        }

    async def fake_weak_word_judge(**kwargs: Any) -> dict[str, Any]:
        seen_judge_issues.append(list(kwargs["actual_issues"]))
        db = kwargs["db"]
        graph_run = GraphRunLog(
            graph_key="qure_eval_weak_word_judge_graph",
            status="success",
            actor_user_id=kwargs["actor_user_id"],
            project_id=kwargs["project_id"],
            source="qure_eval",
            finished_at=datetime.now(UTC),
            final_state_preview={"stub": True},
        )
        db.add(graph_run)
        await db.flush()
        weak_word = str(kwargs["weak_word"])
        match = weak_word in {"fast", "large"}
        passed = weak_word in {"adequate", "fast", "large"}
        verdict_match = kwargs["expected_verdict"] == kwargs["actual_verdict"]
        return {
            "judge_payload": {
                "passed": passed,
                "match": match,
                "score": 1.0 if match else 0.0,
                "verdict_match": verdict_match,
                "weak_word_match": match,
                "matched_issue_indices": [0] if match else [],
                "rationale": "stub",
                "ok": True,
            },
            "judge_graph_run_id": graph_run.id,
        }

    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_validation_eval_graph",
        fake_validation_eval_graph,
    )
    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_qure_eval_weak_word_judge_graph",
        fake_weak_word_judge,
    )

    response = await client.post(
        "/admin/qure-eval/runs",
        headers=headers,
        data={"project_id": project_id, "row_limit": "4"},
        files={"file": ("QuRE.csv", qure_csv(), "text/csv")},
    )
    assert response.status_code == 201
    run_id = response.json()["id"]

    detail = None
    for _ in range(10):
        detail_response = await client.get(f"/admin/qure-eval/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "success":
            break
        await asyncio.sleep(0.1)

    assert detail is not None
    assert detail["status"] == "success"
    assert len(detail["case_results"]) == 4
    by_source_id = {item["source_id"]: item for item in detail["case_results"]}
    assert seen_settings
    assert all(
        settings == {
            "core_rules": True,
            "custom_rules": False,
            "context_questions": False,
        }
        for settings in seen_settings
    )
    assert len(seen_judge_issues) == 4
    assert [] in seen_judge_issues
    assert by_source_id["2"]["status"] == "failed"
    assert by_source_id["2"]["metrics"]["verdict_match"] is True
    assert by_source_id["3"]["status"] == "passed"
    assert by_source_id["3"]["metrics"]["verdict_match"] is False
    assert detail["summary_metrics"]["verdict_accuracy"] == 0.75
    assert detail["summary_metrics"]["weak_word_f1"] == 0.5
    assert detail["summary_metrics"]["judge_pass_rate"] == 0.75
    assert detail["summary_metrics"]["judge_errors"] == 0
    assert detail["summary_metrics"]["verdict_confusion_matrix"]["ok"]["needs_rework"] == 1

    export_response = await client.get(
        f"/admin/qure-eval/runs/{run_id}/export",
        headers=headers,
        params={"format": "csv"},
    )
    assert export_response.status_code == 200
    assert "weak_word" in export_response.text
    assert "fast" in export_response.text


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_qure_eval_marks_case_error_when_judge_has_no_valid_decision(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = await register_and_login(
        client,
        email="qure-eval-judge-error@example.com",
        full_name="QuRE Eval Judge Error Admin",
    )
    project_id = await create_project(client, token, name="QuRE Eval Judge Error")
    headers = {"Authorization": f"Bearer {token}"}

    async def fake_validation_eval_graph(**kwargs: Any) -> dict[str, Any]:
        db = kwargs["db"]
        graph_run = GraphRunLog(
            graph_key="validation_graph",
            status="success",
            actor_user_id=kwargs["actor_user_id"],
            project_id=kwargs["project_id"],
            source="qure_eval",
            finished_at=datetime.now(UTC),
            final_state_preview={"stub": True},
        )
        db.add(graph_run)
        await db.flush()
        return {
            "verdict": "approved",
            "issues": [],
            "questions": [],
            "graph_run_id": graph_run.id,
            "llm_diagnostics": [{"prompt_key": "task-validation-core", "ok": True}],
            "core_issues": [],
            "core_questions": [],
        }

    async def fake_invalid_judge(**kwargs: Any) -> dict[str, Any]:
        db = kwargs["db"]
        graph_run = GraphRunLog(
            graph_key="qure_eval_weak_word_judge_graph",
            status="success",
            actor_user_id=kwargs["actor_user_id"],
            project_id=kwargs["project_id"],
            source="qure_eval",
            finished_at=datetime.now(UTC),
            final_state_preview={"stub": True},
        )
        db.add(graph_run)
        await db.flush()
        return {
            "judge_payload": {
                "ok": False,
                "rationale": "Judge did not return a valid QuRE decision.",
            },
            "judge_graph_run_id": graph_run.id,
        }

    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_validation_eval_graph",
        fake_validation_eval_graph,
    )
    monkeypatch.setattr(
        "app.services.admin_qure_eval_service.run_qure_eval_weak_word_judge_graph",
        fake_invalid_judge,
    )

    response = await client.post(
        "/admin/qure-eval/runs",
        headers=headers,
        data={"project_id": project_id, "row_limit": "1"},
        files={
            "file": (
                "QuRE.csv",
                "id,requirement,defect,weak_word\n1,The system shall respond fast.,defect,fast\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 201
    run_id = response.json()["id"]

    detail = None
    for _ in range(10):
        detail_response = await client.get(f"/admin/qure-eval/runs/{run_id}", headers=headers)
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] == "success":
            break
        await asyncio.sleep(0.1)

    assert detail is not None
    assert detail["status"] == "success"
    case_result = detail["case_results"][0]
    assert case_result["status"] == "error"
    assert case_result["metrics"]["judge_ok"] is False
    assert case_result["metrics"]["result_source"] == "llm_judge"
    assert detail["summary_metrics"]["errors"] == 1
    assert detail["summary_metrics"]["judge_errors"] == 1
    assert detail["summary_metrics"]["validator_errors"] == 0


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_qure_eval_rejects_invalid_upload(
    client: AsyncClient,
) -> None:
    token = await register_and_login(
        client,
        email="qure-eval-invalid@example.com",
        full_name="QuRE Eval Invalid Admin",
    )
    project_id = await create_project(client, token, name="QuRE Eval Invalid")
    response = await client.post(
        "/admin/qure-eval/runs",
        headers={"Authorization": f"Bearer {token}"},
        data={"project_id": project_id, "row_limit": "2"},
        files={
            "file": (
                "adapted.csv",
                "case_external_id,title,content\n1,title,content\n",
                "text/csv",
            )
        },
    )

    assert response.status_code == 422
