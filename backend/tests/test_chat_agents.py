from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from app.agents.chat_agents.base import ChatAgentContext, ChatAgentMetadata
from app.agents.chat_agents.change_tracker_agent import ChangeTrackerAgent
from app.agents.chat_agents.llm import ChatAgentLLMProfile, build_chat_model
from app.agents.chat_agents.question_agent import QuestionAgent
from app.agents.chat_agents.registry import parse_requested_agent
from app.agents.chat_graph import run_chat_graph
from app.agents.state import ChatState
from app.agents.subgraph_registry import (
    AgentSubgraphSpec,
    list_agent_subgraph_metadata,
    register_agent_subgraph,
    reset_agent_subgraph_registry,
)
from app.services.llm_runtime_service import LLMInvocationResult


@pytest.fixture(autouse=True)
def reset_subgraph_registry_fixture() -> None:
    reset_agent_subgraph_registry()


def test_builtin_agent_subgraphs_are_discoverable() -> None:
    agent_keys = {item.key for item in list_agent_subgraph_metadata()}

    assert {"qa", "change-tracker", "manager"} <= agent_keys


def test_parse_requested_agent_prefix() -> None:
    requested_agent, routed_content = parse_requested_agent("@change Update the API contract")

    assert requested_agent == "change"
    assert routed_content == "Update the API contract"


def test_parse_requested_agent_supports_slash_prefix() -> None:
    requested_agent, routed_content = parse_requested_agent(
        "/qaagent Какие статусы считаются терминальными?",
    )

    assert requested_agent == "qaagent"
    assert routed_content == "Какие статусы считаются терминальными?"


def test_build_chat_model_supports_local_provider() -> None:
    llm = build_chat_model(
        ChatAgentLLMProfile(
            provider="ollama",
            model="llama3.1",
            base_url="http://localhost:11434",
            temperature=0.1,
        )
    )

    assert type(llm).__name__ == "ChatOllama"
    assert getattr(llm, "model", None) == "llama3.1"


def test_build_chat_model_supports_openai_compatible_endpoint() -> None:
    llm = build_chat_model(
        ChatAgentLLMProfile(
            provider="openai_compatible",
            model="mistral-small",
            api_key="local-key",
            base_url="http://127.0.0.1:1234/v1",
            temperature=0.0,
        )
    )

    assert type(llm).__name__ == "ChatOpenAI"
    assert getattr(llm, "model_name", None) == "mistral-small"
    assert getattr(llm, "openai_api_base", None) == "http://127.0.0.1:1234/v1"


@pytest.mark.asyncio
async def test_question_agent_uses_live_llm_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    llm_calls: list[str] = []

    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        llm_calls.append(str(kwargs["agent_key"]))
        if kwargs["agent_key"] == "qa-planner":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"analysis_mode":"direct","needs_rag":false,'
                    '"needs_verification":true,"retrieval_query":null,'
                    '"retrieval_limit":2,"focus_points":["api evolution"],'
                    '"canonical_question_hint":null}'
                ),
                provider_config_id="provider-1",
                provider_kind="openrouter",
                model="openai/gpt-4o-mini",
                latency_ms=30,
                prompt_tokens=6,
                completion_tokens=12,
                total_tokens=18,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-answer":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"answer":"Нужно развивать API через версионируемый контракт и явные '
                    'события синхронизации.","confidence":"high",'
                    '"canonical_question":null}'
                ),
                provider_config_id="provider-1",
                provider_kind="openrouter",
                model="openai/gpt-4o-mini",
                latency_ms=123,
                prompt_tokens=10,
                completion_tokens=20,
                total_tokens=30,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-verifier":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"final_answer":"Нужно развивать API через версионируемый контракт '
                    'и явные события синхронизации.","confidence":"high",'
                    '"grounded":true,"canonical_question":null}'
                ),
                provider_config_id="provider-1",
                provider_kind="openrouter",
                model="openai/gpt-4o-mini",
                latency_ms=40,
                prompt_tokens=8,
                completion_tokens=12,
                total_tokens=20,
                estimated_cost_usd=None,
            )
        return LLMInvocationResult(
            ok=False,
            text=None,
            provider_config_id="provider-1",
            provider_kind="openrouter",
            model="openai/gpt-4o-mini",
            latency_ms=0,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            estimated_cost_usd=None,
            error_message="unexpected agent key",
        )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    result = await QuestionAgent().handle(
        ChatAgentContext(
            db=object(),  # type: ignore[arg-type]
            actor_user_id="user-1",
            task_id="task-1",
            project_id="project-1",
            task_title="API sync",
            task_status="draft",
            task_content="Backend and frontend should use one schema.",
            message_type="question",
            message_content="How should the API evolve?",
            validation_result=None,
            related_tasks=[],
        )
    )

    assert result.response == "Нужно развивать API через версионируемый контракт и явные события синхронизации."
    assert result.source_ref["provider_kind"] == "openrouter"
    assert result.source_ref["answer_confidence"] == "high"
    assert llm_calls == ["qa-planner", "qa-answer", "qa-verifier"]


@pytest.mark.asyncio
async def test_question_agent_marks_low_confidence_answers_for_validation_backlog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_calls: list[str] = []

    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        llm_calls.append(str(kwargs["agent_key"]))
        if kwargs["agent_key"] == "qa-planner":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"analysis_mode":"deep","needs_rag":true,'
                    '"needs_verification":true,'
                    '"retrieval_query":"статусы синхронизации",'
                    '"retrieval_limit":4,'
                    '"focus_points":["terminal statuses"],'
                    '"canonical_question_hint":"Какие статусы синхронизируются между системами?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=25,
                prompt_tokens=8,
                completion_tokens=12,
                total_tokens=20,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-answer":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"answer":"В задаче не указано, какие статусы считаются итоговыми.",'
                    '"confidence":"low",'
                    '"canonical_question":"Какие статусы синхронизируются между системами?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=80,
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
    result = await QuestionAgent().handle(
        ChatAgentContext(
            db=object(),  # type: ignore[arg-type]
            actor_user_id="user-1",
            task_id="task-1",
            project_id="project-1",
            task_title="API sync",
            task_status="ready_for_dev",
            task_content="Backend and frontend should keep status changes in sync.",
            message_type="question",
            message_content="Как должны синхронизироваться статусы?",
            validation_result=None,
            related_tasks=[],
        )
    )

    assert result.source_ref["answer_confidence"] == "low"
    assert (
        result.source_ref["validation_backlog_question"]
        == "Какие статусы синхронизируются между системами?"
    )
    assert "Вопрос сохранён в базе вопросов" in result.response
    assert llm_calls == ["qa-planner", "qa-answer"]


@pytest.mark.asyncio
async def test_question_agent_uses_qdrant_task_knowledge_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_calls: list[str] = []

    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        llm_calls.append(str(kwargs["agent_key"]))
        if kwargs["agent_key"] == "qa-planner":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"analysis_mode":"deep","needs_rag":true,"needs_verification":true,'
                    '"retrieval_query":"status.changed event",'
                    '"retrieval_limit":4,'
                    '"focus_points":["integration event"],'
                    '"canonical_question_hint":null}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=25,
                prompt_tokens=6,
                completion_tokens=12,
                total_tokens=18,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-answer":
            return LLMInvocationResult(
                ok=True,
                text='{"answer":"Используйте событие status.changed.", "confidence":"high", "canonical_question":null}',
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=40,
                prompt_tokens=10,
                completion_tokens=12,
                total_tokens=22,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-verifier":
            return LLMInvocationResult(
                ok=True,
                text='{"final_answer":"Используйте событие status.changed.", "confidence":"high", "grounded":true, "canonical_question":null}',
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=20,
                prompt_tokens=6,
                completion_tokens=8,
                total_tokens=14,
                estimated_cost_usd=None,
            )
        raise AssertionError(f"Unexpected agent key: {kwargs['agent_key']}")

    async def fake_search_task_knowledge(**kwargs):  # type: ignore[no-untyped-def]
        return [
            Document(
                page_content="Publish event status.changed after every persisted transition.",
                metadata={"chunk_id": "task-1:content"},
            )
        ]

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.search_task_knowledge",
        fake_search_task_knowledge,
    )
    result = await QuestionAgent().handle(
        ChatAgentContext(
            db=object(),  # type: ignore[arg-type]
            actor_user_id="user-1",
            task_id="task-1",
            project_id="project-1",
            task_title="API sync",
            task_status="ready_for_dev",
            task_content="Backend and frontend should keep status changes in sync.",
            message_type="question",
            message_content="Какой event надо публиковать?",
            validation_result=None,
            related_tasks=[],
        )
    )

    assert result.source_ref["collection"] == "task_knowledge"
    assert result.source_ref["chunk_ids"] == ["task-1:content"]
    assert llm_calls == ["qa-planner", "qa-answer", "qa-verifier"]


@pytest.mark.asyncio
async def test_change_tracker_falls_back_to_raw_message_on_bad_llm_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text="not-json",
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o-mini",
            latency_ms=90,
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    result = await ChangeTrackerAgent().handle(
        ChatAgentContext(
            db=object(),  # type: ignore[arg-type]
            actor_user_id="user-1",
            task_id="task-1",
            project_id="project-1",
            task_title="API sync",
            task_status="draft",
            task_content="Backend and frontend should use one schema.",
            message_type="change_proposal",
            message_content="Update the API contract",
            validation_result=None,
            related_tasks=[],
        )
    )

    assert result.proposal_text == "Update the API contract"
    assert result.message_type == "agent_proposal"


@pytest.mark.asyncio
async def test_change_tracker_marks_duplicate_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_find_duplicate_proposal(**kwargs):  # type: ignore[no-untyped-def]
        return {
            "proposal_id": "proposal-1",
            "task_id": "task-2",
            "score": 0.97,
        }

    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.find_duplicate_proposal",
        fake_find_duplicate_proposal,
    )

    result = await ChangeTrackerAgent().handle(
        ChatAgentContext(
            db=None,
            actor_user_id="user-1",
            task_id="task-1",
            project_id="project-1",
            task_title="API sync",
            task_status="draft",
            task_content="Backend and frontend should use one schema.",
            message_type="change_proposal",
            message_content="Update the API contract",
            validation_result=None,
            related_tasks=[],
        )
    )

    assert result.message_type == "agent_answer"
    assert result.source_ref["duplicate_proposal"] is True
    assert result.source_ref["duplicate_task_id"] == "task-2"


@pytest.mark.asyncio
async def test_forced_change_agent_can_handle_general_message() -> None:
    requested_agent, routed_content = parse_requested_agent("@change Update the API contract")

    state = await run_chat_graph(
        db=None,
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="API sync",
        task_status="draft",
        task_content="Backend and frontend should use one schema.",
        message_type="general",
        message_content=routed_content,
        validation_result=None,
        related_tasks=[],
        requested_agent=requested_agent,
        raw_message_content="@change Update the API contract",
    )

    assert state["agent_name"] == "ChangeTrackerAgent"
    assert state["message_type"] == "agent_proposal"
    assert state["proposal_text"] == "Update the API contract"
    assert state["source_ref"]["agent_key"] == "change-tracker"
    assert state["source_ref"]["routing_mode"] == "forced"


@pytest.mark.asyncio
async def test_forced_qaagent_command_routes_to_qa_subgraph() -> None:
    requested_agent, routed_content = parse_requested_agent(
        "/qaagent Какие статусы считаются терминальными?",
    )

    state = await run_chat_graph(
        db=None,
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="Status sync",
        task_status="ready_for_dev",
        task_content="Backend and frontend should keep statuses in sync.",
        message_type="general",
        message_content=routed_content,
        validation_result={"verdict": "approved", "questions": []},
        related_tasks=[],
        requested_agent=requested_agent,
        raw_message_content="/qaagent Какие статусы считаются терминальными?",
    )

    assert state["agent_name"] == "QAAgent"
    assert state["message_type"] == "agent_answer"
    assert state["source_ref"]["agent_key"] == "qa"
    assert state["source_ref"]["routing_mode"] == "forced"


@pytest.mark.asyncio
async def test_unknown_forced_agent_returns_directory_message() -> None:
    requested_agent, routed_content = parse_requested_agent("@risk Check the integration path")

    state = await run_chat_graph(
        db=None,
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="Risk check",
        task_status="draft",
        task_content="Need to understand rollout risks.",
        message_type="general",
        message_content=routed_content,
        validation_result=None,
        related_tasks=[],
        requested_agent=requested_agent,
        raw_message_content="@risk Check the integration path",
    )

    assert state["agent_name"] == "ManagerAgent"
    assert "risk" in state["response"]
    assert "не зарегистрирован" in state["response"]
    assert state["source_ref"]["requested_agent"] == "risk"
    assert state["source_ref"]["routing_mode"] == "forced"


@pytest.mark.asyncio
async def test_background_question_skips_ai_response() -> None:
    state = await run_chat_graph(
        db=None,
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="API sync",
        task_status="draft",
        task_content="Backend and frontend should use one schema for task updates.",
        message_type="question",
        message_content="Как погода сегодня?",
        validation_result=None,
        requested_agent=None,
        raw_message_content="Как погода сегодня?",
    )

    assert state["ai_response_required"] is False
    assert "agent_name" not in state
    assert "response" not in state


@pytest.mark.asyncio
async def test_llm_routing_can_skip_non_task_question(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        assert kwargs["agent_key"] == "chat-routing"
        return LLMInvocationResult(
            ok=True,
            text='{"task_related": false, "reason": "smalltalk"}',
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o-mini",
            latency_ms=25,
            prompt_tokens=10,
            completion_tokens=8,
            total_tokens=18,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )

    state = await run_chat_graph(
        db=object(),
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="API sync",
        task_status="draft",
        task_content="Backend and frontend should use one schema for task updates.",
        message_type="question",
        message_content="Как настроение в команде сегодня?",
        validation_result=None,
        requested_agent=None,
        raw_message_content="Как настроение в команде сегодня?",
    )

    assert state["ai_response_required"] is False
    assert "agent_name" not in state


@pytest.mark.asyncio
async def test_llm_routing_can_send_task_question_to_qa(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        if kwargs["agent_key"] == "chat-routing":
            return LLMInvocationResult(
                ok=True,
                text='{"task_related": true, "reason": "requirements question"}',
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=20,
                prompt_tokens=10,
                completion_tokens=8,
                total_tokens=18,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-planner":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"analysis_mode":"deep","needs_rag":true,'
                    '"needs_verification":true,'
                    '"retrieval_query":"терминальные статусы интеграции",'
                    '"retrieval_limit":4,'
                    '"focus_points":["terminal statuses"],'
                    '"canonical_question_hint":"Какие статусы считаются терминальными?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=20,
                prompt_tokens=8,
                completion_tokens=8,
                total_tokens=16,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-answer":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"answer":"Терминальные статусы нужно перечислить отдельно в постановке.",'
                    '"confidence":"low",'
                    '"canonical_question":"Какие статусы считаются терминальными?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=40,
                prompt_tokens=20,
                completion_tokens=18,
                total_tokens=38,
                estimated_cost_usd=None,
            )
        raise AssertionError(f"Unexpected agent key: {kwargs['agent_key']}")

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                id=identifier,
                project_id="project-1",
                validation_result={"verdict": "approved", "questions": []},
            )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    async def fake_record_chat_question(*args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    monkeypatch.setattr(
        "app.services.validation_question_service.ValidationQuestionService.record_chat_question",
        fake_record_chat_question,
    )

    state = await run_chat_graph(
        db=FakeDB(),
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        source_message_id="message-1",
        task_title="Status sync",
        task_status="ready_for_dev",
        task_content="Backend and frontend should keep statuses in sync.",
        message_type="question",
        message_content="Нужно ли отдельно перечислить терминальные статусы для интеграции?",
        validation_result={"verdict": "approved", "questions": []},
        related_tasks=[],
        requested_agent=None,
        raw_message_content="Нужно ли отдельно перечислить терминальные статусы для интеграции?",
    )

    assert state["ai_response_required"] is True
    assert state["agent_name"] == "QAAgent"
    assert state["source_ref"]["answer_confidence"] == "low"


@pytest.mark.asyncio
async def test_chat_graph_persists_low_confidence_question_via_langgraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        if kwargs["agent_key"] == "qa-planner":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"analysis_mode":"deep","needs_rag":true,'
                    '"needs_verification":true,'
                    '"retrieval_query":"терминальные статусы",'
                    '"retrieval_limit":4,'
                    '"focus_points":["terminal statuses"],'
                    '"canonical_question_hint":"Какие статусы считаются терминальными?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=20,
                prompt_tokens=8,
                completion_tokens=10,
                total_tokens=18,
                estimated_cost_usd=None,
            )
        if kwargs["agent_key"] == "qa-answer":
            return LLMInvocationResult(
                ok=True,
                text=(
                    '{"answer":"В задаче не хватает данных о терминальных статусах.",'
                    '"confidence":"low",'
                    '"canonical_question":"Какие статусы считаются терминальными?"}'
                ),
                provider_config_id="provider-1",
                provider_kind="openai",
                model="gpt-4o-mini",
                latency_ms=55,
                prompt_tokens=12,
                completion_tokens=18,
                total_tokens=30,
                estimated_cost_usd=None,
            )
        raise AssertionError(f"Unexpected agent key: {kwargs['agent_key']}")

    audit_events: list[str] = []

    async def fake_record_chat_question(*args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(
            id="validation-question-1",
            question_text="Какие статусы считаются терминальными?",
        )

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                id=identifier,
                project_id="project-1",
                validation_result={
                    "verdict": "approved",
                    "validated_at": "2026-04-18T10:00:00+00:00",
                },
            )

    def fake_audit_record(*args, **kwargs):  # type: ignore[no-untyped-def]
        audit_events.append(str(kwargs["event_type"]))

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.validation_question_service.ValidationQuestionService.record_chat_question",
        fake_record_chat_question,
    )
    monkeypatch.setattr("app.services.audit_service.AuditService.record", fake_audit_record)

    state = await run_chat_graph(
        db=FakeDB(),
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        source_message_id="message-1",
        task_title="Status sync",
        task_status="ready_for_dev",
        task_content="Backend and frontend should keep statuses in sync.",
        message_type="question",
        message_content="Какие статусы считаются терминальными?",
        validation_result={"verdict": "approved", "questions": []},
        related_tasks=[{"task_id": "task-2", "title": "Status mapping"}],
        requested_agent=None,
        raw_message_content="Какие статусы считаются терминальными?",
    )

    assert state["source_ref"]["validation_backlog_saved"] is True
    assert state["source_ref"]["validation_question_id"] == "validation-question-1"
    assert state["source_ref"]["answer_confidence"] == "low"
    assert "chat.validation_question_recorded" in audit_events


@pytest.mark.asyncio
async def test_chat_graph_creates_proposal_via_langgraph(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text=(
                '{"proposal_text":"Update the API contract",'
                '"acknowledgement":"Изменение оформлено."}'
            ),
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o-mini",
            latency_ms=40,
            prompt_tokens=10,
            completion_tokens=12,
            total_tokens=22,
            estimated_cost_usd=None,
        )

    audit_events: list[str] = []

    async def fake_create_from_message(*args, **kwargs):  # type: ignore[no-untyped-def]
        return SimpleNamespace(id="proposal-1")

    def fake_audit_record(*args, **kwargs):  # type: ignore[no-untyped-def]
        audit_events.append(str(kwargs["event_type"]))

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_chat",
        fake_invoke_chat,
    )
    monkeypatch.setattr(
        "app.services.proposal_service.ProposalService.create_from_message",
        fake_create_from_message,
    )
    monkeypatch.setattr("app.services.audit_service.AuditService.record", fake_audit_record)

    state = await run_chat_graph(
        db=object(),
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        source_message_id="message-1",
        task_title="API sync",
        task_status="draft",
        task_content="Backend and frontend should use one schema.",
        message_type="change_proposal",
        message_content="Update the API contract",
        validation_result=None,
        related_tasks=[{"task_id": "task-2", "title": "Schema sync"}],
        requested_agent=None,
        raw_message_content="Update the API contract",
    )

    assert state["message_type"] == "agent_proposal"
    assert state["source_ref"]["proposal_id"] == "proposal-1"
    assert "chat.proposal_requested" in audit_events


@pytest.mark.asyncio
async def test_external_subgraph_is_used_for_forced_routing() -> None:
    async def can_handle(context: ChatAgentContext) -> bool:
        return "#risk" in context.message_content.lower()

    async def run_external(context: ChatAgentContext, routing_mode: str) -> ChatState:
        return {
            "agent_name": "RiskAgent",
            "message_type": "agent_answer",
            "response": f"Routing mode: {routing_mode}",
            "source_ref": {"collection": "messages"},
        }

    register_agent_subgraph(
        AgentSubgraphSpec(
            metadata=ChatAgentMetadata(
                key="risk",
                name="RiskAgent",
                description="Анализирует риски.",
                aliases=("risk-review",),
                priority=40,
            ),
            can_handle=can_handle,
            runner=run_external,
        )
    )

    requested_agent, routed_content = parse_requested_agent("@risk Review rollout")
    state = await run_chat_graph(
        db=None,
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="Rollout",
        task_status="draft",
        task_content="Need a release risk check.",
        message_type="general",
        message_content=routed_content,
        validation_result=None,
        related_tasks=[],
        requested_agent=requested_agent,
        raw_message_content="@risk Review rollout",
    )

    assert state["agent_name"] == "RiskAgent"
    assert state["response"] == "Routing mode: forced"
    assert state["source_ref"]["agent_key"] == "risk"


@pytest.mark.asyncio
async def test_external_subgraph_is_used_for_auto_routing() -> None:
    async def can_handle(context: ChatAgentContext) -> bool:
        return "#risk" in context.message_content.lower()

    async def run_external(context: ChatAgentContext, routing_mode: str) -> ChatState:
        return {
            "agent_name": "RiskAgent",
            "message_type": "agent_answer",
            "response": f"Auto route for {context.task_title}",
            "source_ref": {"collection": "messages"},
        }

    register_agent_subgraph(
        AgentSubgraphSpec(
            metadata=ChatAgentMetadata(
                key="risk",
                name="RiskAgent",
                description="Анализирует риски.",
                aliases=("risk-review",),
                priority=40,
            ),
            can_handle=can_handle,
            runner=run_external,
        )
    )

    state = await run_chat_graph(
        db=None,
        task_id="task-1",
        project_id="project-1",
        actor_user_id="user-1",
        task_title="Release",
        task_status="draft",
        task_content="Need a risk review before production rollout.",
        message_type="general",
        message_content="Please review #risk before release",
        validation_result=None,
        related_tasks=[],
        requested_agent=None,
        raw_message_content="Please review #risk before release",
    )

    assert state["ai_response_required"] is True
    assert state["agent_name"] == "RiskAgent"
    assert state["response"] == "Auto route for Release"
    assert state["source_ref"]["routing_mode"] == "auto"
