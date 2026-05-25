from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from app.agents.rag_eval_judge_graph import run_rag_eval_judge_graph
from app.agents.validation_eval_question_judge_graph import (
    run_validation_eval_question_judge_graph,
)
from app.schemas.admin_adaptation_eval import AdaptationEvalRunConfig
from app.schemas.admin_rag_eval import RagEvalRunConfig
from app.schemas.admin_validation_eval import ValidationEvalRunConfig
from app.services.admin_adaptation_eval_service import AdminAdaptationEvalService
from app.services.admin_rag_eval_service import AdminRagEvalService
from app.services.admin_validation_eval_service import AdminValidationEvalService
from app.services.llm_runtime_service import LLMInvocationResult

VALIDATION_EVAL_CORE_VARIANT = {
    "key": "core_rules",
    "validation_node_settings": {
        "core_rules": True,
        "custom_rules": False,
        "context_questions": False,
    },
    "prompt_version_ids": {},
}


def make_eval_config(config_cls: type, **kwargs: Any) -> Any:
    if config_cls is ValidationEvalRunConfig:
        kwargs.setdefault("variants", [VALIDATION_EVAL_CORE_VARIANT])
    return config_cls(**kwargs)


@pytest.mark.parametrize(
    "config_cls",
    [RagEvalRunConfig, ValidationEvalRunConfig, AdaptationEvalRunConfig],
)
def test_judge_provider_config_ids_accept_empty_or_one_to_three_unique(
    config_cls: type,
) -> None:
    assert make_eval_config(config_cls).judge_provider_config_ids == []
    assert make_eval_config(
        config_cls, judge_provider_config_ids=["provider-1"]
    ).judge_provider_config_ids == ["provider-1"]
    assert make_eval_config(
        config_cls, judge_provider_config_ids=["provider-1", "provider-2"]
    ).judge_provider_config_ids == ["provider-1", "provider-2"]
    assert make_eval_config(
        config_cls, judge_provider_config_ids=["provider-1", "provider-2", "provider-3"]
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
        make_eval_config(config_cls, judge_provider_config_ids=provider_ids)


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
            variants=[VALIDATION_EVAL_CORE_VARIANT],
            judge_provider_config_ids=["provider-1", "provider-2", "provider-3"],
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


@pytest.mark.asyncio
async def test_adaptation_multi_judge_forwards_each_provider_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_provider_ids: list[str | None] = []

    async def fake_invoke_chat(*args, **kwargs):  # type: ignore[no-untyped-def]
        provider_config_id = kwargs.get("provider_config_id")
        seen_provider_ids.append(provider_config_id)
        return LLMInvocationResult(
            ok=True,
            text=(
                '{"matches":[{"expected_index":0,"actual_index":0,'
                '"match":true,"confidence":0.91,"reason":"same meaning"}],'
                '"unmatched_expected_indices":[],"unmatched_actual_indices":[],"ok":true}'
            ),
            provider_config_id=provider_config_id,
            provider_kind="openai",
            model=f"model-{provider_config_id}",
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
        expected_items=[{"index": 0, "text": "Какой SLA нужен?"}],
        actual_items=[{"index": 0, "text": "Какое значение SLA требуется?"}],
    )

    payload = state["judge_payload"]
    assert seen_provider_ids == ["provider-1", "provider-2", "provider-3"]
    assert [run["provider_config_id"] for run in payload["judge_runs"]] == [
        "provider-1",
        "provider-2",
        "provider-3",
    ]
    assert payload["provider_config_id"] == "provider-1"


@pytest.mark.asyncio
async def test_rag_judge_graph_forwards_provider_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_provider_ids: list[str | None] = []

    async def fake_invoke_chat(*args, **kwargs):  # type: ignore[no-untyped-def]
        provider_config_id = kwargs.get("provider_config_id")
        seen_provider_ids.append(provider_config_id)
        return LLMInvocationResult(
            ok=True,
            text=(
                '{"groundedness":"grounded","correctness":"correct",'
                '"unsupported_claims":[],"rationale":"ok"}'
            ),
            provider_config_id=provider_config_id,
            provider_kind="openai",
            model=f"model-{provider_config_id}",
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

    state = await run_rag_eval_judge_graph(
        db=SimpleNamespace(),
        actor_user_id="user-1",
        task_id="task-1",
        project_id="project-1",
        question="Q",
        expected_answer="A",
        answer_text="A",
        retrieved_chunks=[],
        provider_config_id="provider-2",
    )

    assert seen_provider_ids == ["provider-2"]
    assert state["judge_payload"]["provider_config_id"] == "provider-2"


@pytest.mark.asyncio
async def test_validation_question_judge_graph_forwards_provider_to_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_provider_ids: list[str | None] = []

    async def fake_invoke_chat(*args, **kwargs):  # type: ignore[no-untyped-def]
        provider_config_id = kwargs.get("provider_config_id")
        seen_provider_ids.append(provider_config_id)
        return LLMInvocationResult(
            ok=True,
            text=(
                '{"relevance":1,"specificity":0.9,"actionability":0.8,'
                '"novelty":0.7,"rationale":"ok"}'
            ),
            provider_config_id=provider_config_id,
            provider_kind="openai",
            model=f"model-{provider_config_id}",
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

    async def fake_run_traced_graph(*, graph, input_state, **kwargs):  # type: ignore[no-untyped-def]
        return await graph.ainvoke(input_state)

    monkeypatch.setattr(
        "app.agents.validation_eval_question_judge_graph.run_traced_graph",
        fake_run_traced_graph,
    )

    state = await run_validation_eval_question_judge_graph(
        db=SimpleNamespace(),
        actor_user_id="user-1",
        project_id="project-1",
        task_title="Task",
        task_content="Content",
        expected_questions=["Q"],
        actual_questions=["Q"],
        provider_config_id="provider-3",
    )

    assert seen_provider_ids == ["provider-3"]
    assert state["judge_payload"]["provider_config_id"] == "provider-3"
