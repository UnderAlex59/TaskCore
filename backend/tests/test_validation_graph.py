from __future__ import annotations

import pytest
from langchain_core.documents import Document

from app.agents.validation_graph import run_validation_graph
from app.services.llm_runtime_service import LLMInvocationResult


@pytest.mark.asyncio
async def test_validation_graph_respects_disabled_nodes() -> None:
    result = await run_validation_graph(
        project_id="project-1",
        title="API",
        content="Коротко.",
        tags=[],
        custom_rules=[
            {
                "title": "Security review",
                "description": "Task must mention OAuth scopes and audit logging",
            }
        ],
        related_tasks=[{"task_id": "task-2", "title": "Similar task"}],
        attachment_names=[],
        validation_node_settings={
            "core_rules": False,
            "custom_rules": False,
            "context_questions": False,
        },
    )

    assert result["verdict"] == "approved"
    assert result["issues"] == []
    assert result["questions"] == []


@pytest.mark.asyncio
async def test_validation_graph_stops_after_core_rule_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_calls = 0

    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        nonlocal llm_calls
        llm_calls += 1
        assert kwargs["agent_key"] == "task-validation"
        return LLMInvocationResult(
            ok=True,
            text=(
                '{"issues":[{"code":"missing_terminal_statuses","severity":"high",'
                '"message":"Не перечислены терминальные статусы и не описан запуск повторной синхронизации."}],'
                '"questions":["Кто инициирует повторную синхронизацию статусов?"]}'
            ),
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o-mini",
            latency_ms=90,
            prompt_tokens=30,
            completion_tokens=40,
            total_tokens=70,
            estimated_cost_usd=None,
        )

    async def fake_search_project_questions(**kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Qdrant search must not run after core validation errors")

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.search_project_questions",
        fake_search_project_questions,
    )

    result = await run_validation_graph(
        db=object(),
        actor_user_id="user-1",
        task_id="task-1",
        project_id="project-1",
        title="Status sync contract",
        content=(
            "When an operator changes the order status in the CRM, the backend should persist the "
            "new value, publish an event for downstream services and expose the updated status in the UI."
        ),
        tags=["integration"],
        custom_rules=[
            {
                "title": "Status lifecycle",
                "description": "Task must clearly define terminal statuses and rerun rules",
            }
        ],
        related_tasks=[{"task_id": "task-2", "title": "Status mapping"}],
        attachment_names=[],
    )

    assert result["verdict"] == "needs_rework"
    assert result["issues"] == [
        {
            "code": "missing_terminal_statuses",
            "severity": "high",
            "message": "Не перечислены терминальные статусы и не описан запуск повторной синхронизации.",
        }
    ]
    assert result["questions"] == ["Кто инициирует повторную синхронизацию статусов?"]
    assert llm_calls == 1


@pytest.mark.asyncio
async def test_validation_graph_reaches_context_stage_only_after_clean_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_stage_payloads = iter(
        [
            '{"issues":[],"questions":["Нужно ли фиксировать SLA обновления?"]}',
            '{"issues":[]}',
            '{"questions":["Какие статусы считаются источником истины?"]}',
        ]
    )

    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text=next(llm_stage_payloads),
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o-mini",
            latency_ms=50,
            prompt_tokens=20,
            completion_tokens=20,
            total_tokens=40,
            estimated_cost_usd=None,
        )

    async def fake_search_project_questions(**kwargs):  # type: ignore[no-untyped-def]
        return [Document(page_content="Какие статусы считаются терминальными?")]

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.search_project_questions",
        fake_search_project_questions,
    )

    result = await run_validation_graph(
        db=object(),
        actor_user_id="user-1",
        task_id="task-1",
        project_id="project-1",
        title="Status sync contract",
        content=(
            "When an operator changes the order status in the CRM, the backend should persist the "
            "new value, publish an event for downstream services and expose the updated status in the UI."
        ),
        tags=["integration"],
        custom_rules=[
            {
                "title": "Status lifecycle",
                "description": "Task must clearly define terminal statuses and rerun rules",
            }
        ],
        related_tasks=[{"task_id": "task-2", "title": "Status mapping"}],
        attachment_names=[],
    )

    assert result["verdict"] == "approved"
    assert result["issues"] == []
    assert result["questions"] == [
        "Нужно ли фиксировать SLA обновления?",
        "Какие статусы считаются источником истины?",
        "Какие статусы считаются терминальными?",
    ]


@pytest.mark.asyncio
async def test_validation_graph_appends_qdrant_project_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_project_questions(**kwargs):  # type: ignore[no-untyped-def]
        return [
            Document(page_content="Какие статусы считаются терминальными?"),
            Document(page_content="Какие статусы считаются терминальными?"),
        ]

    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.search_project_questions",
        fake_search_project_questions,
    )

    result = await run_validation_graph(
        project_id="project-1",
        title="Status sync",
        content=(
            "When an operator changes the order status in the CRM, the backend should persist the "
            "new value and publish an event for downstream services."
        ),
        tags=["integration"],
        custom_rules=[],
        related_tasks=[],
        attachment_names=[],
    )

    assert "Какие статусы считаются терминальными?" in result["questions"]
