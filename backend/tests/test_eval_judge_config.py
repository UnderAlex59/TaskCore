from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.admin_adaptation_eval import AdaptationEvalRunConfig
from app.schemas.admin_rag_eval import RagEvalRunConfig
from app.schemas.admin_validation_eval import ValidationEvalRunConfig
from app.services.admin_adaptation_eval_service import AdminAdaptationEvalService
from app.services.admin_rag_eval_service import AdminRagEvalService
from app.services.admin_validation_eval_service import AdminValidationEvalService


@pytest.mark.parametrize(
    "config_cls",
    [RagEvalRunConfig, ValidationEvalRunConfig, AdaptationEvalRunConfig],
)
def test_judge_provider_config_ids_accept_empty_or_one_to_three_unique(
    config_cls: type,
) -> None:
    assert config_cls().judge_provider_config_ids == []
    assert config_cls(
        judge_provider_config_ids=["provider-1"]
    ).judge_provider_config_ids == ["provider-1"]
    assert config_cls(
        judge_provider_config_ids=["provider-1", "provider-2"]
    ).judge_provider_config_ids == ["provider-1", "provider-2"]
    assert config_cls(
        judge_provider_config_ids=["provider-1", "provider-2", "provider-3"]
    ).judge_provider_config_ids == ["provider-1", "provider-2", "provider-3"]


@pytest.mark.parametrize(
    "config_cls",
    [RagEvalRunConfig, ValidationEvalRunConfig, AdaptationEvalRunConfig],
)
@pytest.mark.parametrize(
    "provider_ids",
    [
        ["provider-1", "provider-1", "provider-2"],
        ["provider-1", "provider-2", "provider-3", "provider-4"],
    ],
)
def test_judge_provider_config_ids_reject_too_many_or_duplicate(
    config_cls: type,
    provider_ids: list[str],
) -> None:
    with pytest.raises(ValidationError):
        config_cls(judge_provider_config_ids=provider_ids)


@pytest.mark.asyncio
async def test_rag_multi_judge_keeps_primary_and_records_secondary_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_provider_ids: list[str | None] = []

    async def fake_judge(**kwargs):  # type: ignore[no-untyped-def]
        provider_config_id = kwargs.get("provider_config_id")
        seen_provider_ids.append(provider_config_id)
        if provider_config_id == "provider-2":
            raise RuntimeError("secondary failed")
        return {
            "judge_payload": {
                "groundedness": "grounded",
                "correctness": "correct",
                "ok": True,
                "provider_config_id": provider_config_id,
            },
            "judge_ok": True,
        }

    monkeypatch.setattr(
        "app.services.admin_rag_eval_service.run_rag_eval_judge_graph",
        fake_judge,
    )
    payload, judge_runs = await AdminRagEvalService._run_rag_judges(
        run=SimpleNamespace(created_by="user-1", project_id="project-1"),
        task=SimpleNamespace(id="task-1"),
        case=SimpleNamespace(question="Q", expected_answer="A"),
        config=RagEvalRunConfig(
            judge_provider_config_ids=["provider-1", "provider-2", "provider-3"]
        ),
        answer_text="answer",
        retrieved_chunks=[],
        db=SimpleNamespace(),
    )

    assert seen_provider_ids == ["provider-1", "provider-2", "provider-3"]
    assert payload["correctness"] == "correct"
    assert len(judge_runs) == 3
    assert judge_runs[1]["ok"] is False
    assert payload["judge_runs"][1]["payload"]["error_message"] == "secondary failed"

    single_payload, single_judge_runs = await AdminRagEvalService._run_rag_judges(
        run=SimpleNamespace(created_by="user-1", project_id="project-1"),
        task=SimpleNamespace(id="task-1"),
        case=SimpleNamespace(question="Q", expected_answer="A"),
        config=RagEvalRunConfig(judge_provider_config_ids=["provider-1"]),
        answer_text="answer",
        retrieved_chunks=[],
        db=SimpleNamespace(),
    )
    assert len(single_judge_runs) == 1
    assert len(single_payload["judge_runs"]) == 1
    assert "judge_agreement" not in single_payload


@pytest.mark.asyncio
async def test_validation_multi_judge_keeps_primary_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_judge(**kwargs):  # type: ignore[no-untyped-def]
        provider_config_id = kwargs.get("provider_config_id")
        if provider_config_id == "provider-3":
            raise RuntimeError("secondary failed")
        return {
            "judge_payload": {
                "relevance": 1.0,
                "specificity": 0.9,
                "actionability": 0.8,
                "novelty": 0.7,
                "ok": True,
                "provider_config_id": provider_config_id,
            },
            "judge_graph_run_id": f"judge-{provider_config_id}",
            "judge_ok": True,
        }

    monkeypatch.setattr(
        "app.services.admin_validation_eval_service.run_validation_eval_question_judge_graph",
        fake_judge,
    )
    payload, judge_runs = await AdminValidationEvalService._run_question_judges(
        db=SimpleNamespace(),
        run=SimpleNamespace(created_by="user-1", project_id="project-1"),
        case=SimpleNamespace(title="Task", content="Content"),
        config=ValidationEvalRunConfig(
            judge_provider_config_ids=["provider-1", "provider-2", "provider-3"]
        ),
        expected_questions=["Q"],
        actual_questions=["Q"],
    )

    assert payload["relevance"] == 1.0
    assert payload["judge_runs"][2]["ok"] is False
    assert payload["judge_agreement"]["score_ranges"]["relevance"] == 0.0
    assert len(judge_runs) == 3


@pytest.mark.asyncio
async def test_adaptation_multi_judge_keeps_primary_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_judge(**kwargs):  # type: ignore[no-untyped-def]
        provider_config_id = kwargs.get("provider_config_id")
        if provider_config_id == "provider-2":
            raise RuntimeError("secondary failed")
        return {
            "judge_payload": {
                "matches": [
                    {
                        "expected_index": 0,
                        "actual_index": 0,
                        "match": True,
                        "confidence": 0.9,
                    }
                ],
                "ok": True,
                "provider_config_id": provider_config_id,
            },
            "judge_graph_run_id": f"judge-{provider_config_id}",
            "judge_ok": True,
        }

    monkeypatch.setattr(
        "app.services.admin_adaptation_eval_service.run_adaptation_eval_match_judge_graph",
        fake_judge,
    )
    state = await AdminAdaptationEvalService._run_match_judges(
        db=SimpleNamespace(),
        actor=SimpleNamespace(id="user-1"),
        project_id="project-1",
        case=SimpleNamespace(external_id="case-1", scenario_type="positive"),
        config=AdaptationEvalRunConfig(
            judge_provider_config_ids=["provider-1", "provider-2", "provider-3"]
        ),
        group_key="capture",
        task_title="Task",
        task_content="Content",
        expected_items=[{"index": 0, "text": "Q"}],
        actual_items=[{"index": 0, "text": "Q"}],
    )

    payload = state["judge_payload"]
    assert payload["matches"][0]["confidence"] == 0.9
    assert payload["judge_runs"][1]["ok"] is False
    assert payload["judge_agreement"]["judge_summaries"][0]["match_count"] == 1
