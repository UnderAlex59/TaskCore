from __future__ import annotations

import pytest

from app.agents.chat_agents.base import ChatAgentContext
from app.agents.chat_agents.change_tracker_agent import ChangeTrackerAgent
from app.agents.chat_agents.llm import ChatAgentLLMProfile, build_chat_model
from app.agents.chat_agents.question_agent import QuestionAgent
from app.agents.chat_agents.registry import (
    list_chat_agents,
    parse_requested_agent,
    reset_chat_agent_registry,
)
from app.agents.chat_graph import run_chat_graph
from app.services.llm_runtime_service import LLMInvocationResult


def test_builtin_chat_agents_are_discoverable() -> None:
    reset_chat_agent_registry()
    agent_keys = {item.key for item in list_chat_agents()}

    assert {"qa", "change-tracker", "manager"} <= agent_keys


def test_parse_requested_agent_prefix() -> None:
    requested_agent, routed_content = parse_requested_agent("@change Update the API contract")

    assert requested_agent == "change"
    assert routed_content == "Update the API contract"


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
    async def fake_invoke_chat(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text="Live answer from the provider",
            provider_config_id="provider-1",
            provider_kind="openrouter",
            model="openai/gpt-4o-mini",
            latency_ms=123,
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr("app.services.llm_runtime_service.LLMRuntimeService.invoke_chat", fake_invoke_chat)
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

    assert result.response == "Live answer from the provider"
    assert result.source_ref["provider_kind"] == "openrouter"


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

    monkeypatch.setattr("app.services.llm_runtime_service.LLMRuntimeService.invoke_chat", fake_invoke_chat)
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
async def test_forced_change_agent_can_handle_general_message() -> None:
    reset_chat_agent_registry()
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
async def test_unknown_forced_agent_returns_directory_message() -> None:
    reset_chat_agent_registry()
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
