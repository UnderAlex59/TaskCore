from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from langchain_core.runnables.graph import Graph

from app.agents.change_tracker_agent_graph import get_change_tracker_agent_graph
from app.agents.chat_graph import get_chat_graph
from app.agents.graph_export import export_agent_graph_images
from app.agents.manager_agent_graph import get_manager_agent_graph
from app.agents.provider_test_graph import get_provider_test_graph, run_provider_test_graph
from app.agents.qa_agent_graph import get_qa_agent_graph
from app.agents.rag_pipeline import get_rag_pipeline_graph
from app.agents.validation_graph import get_validation_graph
from app.agents.vision_test_graph import get_vision_test_graph, run_vision_test_graph
from app.services.llm_runtime_service import LLMInvocationResult


def test_compiled_langgraph_shapes_are_exportable() -> None:
    chat_mermaid = get_chat_graph().get_graph().draw_mermaid()
    qa_mermaid = get_qa_agent_graph().get_graph().draw_mermaid()
    change_tracker_mermaid = get_change_tracker_agent_graph().get_graph().draw_mermaid()
    manager_mermaid = get_manager_agent_graph().get_graph().draw_mermaid()
    validation_mermaid = get_validation_graph().get_graph().draw_mermaid()
    rag_mermaid = get_rag_pipeline_graph().get_graph().draw_mermaid()
    provider_test_mermaid = get_provider_test_graph().get_graph().draw_mermaid()
    vision_test_mermaid = get_vision_test_graph().get_graph().draw_mermaid()

    assert "invoke_agent_subgraph" in chat_mermaid
    assert "invoke_qa_planner" in qa_mermaid
    assert "invoke_qa_answer" in qa_mermaid
    assert "invoke_change_tracker_llm" in change_tracker_mermaid
    assert "build_manager_response" in manager_mermaid
    assert "evaluate_core_rules" in validation_mermaid
    assert "collect_base_chunks" in rag_mermaid
    assert "invoke_provider_test" in provider_test_mermaid
    assert "invoke_vision_test" in vision_test_mermaid


def test_export_agent_graph_images_refreshes_output_dir(
    tmp_path: Path,
    monkeypatch,
) -> None:
    stale_file = tmp_path / "stale.txt"
    stale_file.write_text("old", encoding="utf-8")

    monkeypatch.setattr(Graph, "draw_mermaid_png", lambda self: b"fake-png")

    exported_paths = export_agent_graph_images(tmp_path)

    assert not stale_file.exists()
    assert {path.name for path in exported_paths} == {
        "chat_graph.png",
        "qa_agent_graph.png",
        "change_tracker_agent_graph.png",
        "manager_agent_graph.png",
        "validation_graph.png",
        "rag_pipeline.png",
        "provider_test_graph.png",
        "vision_test_graph.png",
    }
    for path in exported_paths:
        assert path.exists()
        assert path.read_bytes() == b"fake-png"


async def test_provider_test_graph_executes_with_fake_runtime(monkeypatch) -> None:
    async def fake_test_provider(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text="Connectivity OK",
            provider_config_id="provider-1",
            provider_kind="openrouter",
            model="openai/gpt-4o-mini",
            latency_ms=42,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            estimated_cost_usd=None,
        )

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                id=identifier,
                provider_kind="openrouter",
                model="openai/gpt-4o-mini",
            )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.test_provider",
        fake_test_provider,
    )

    result = await run_provider_test_graph(
        db=FakeDB(),
        provider_id="provider-1",
        actor_user_id="admin-1",
    )

    assert result["ok"] is True
    assert result["provider_kind"] == "openrouter"
    assert result["model"] == "openai/gpt-4o-mini"
    assert result["message"] == "Connectivity OK"


async def test_vision_test_graph_executes_with_fake_runtime(monkeypatch) -> None:
    async def fake_invoke_vision(*args, **kwargs) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text="Счет №42\nИтого: 15 000 ₽",
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o",
            latency_ms=73,
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
            estimated_cost_usd=None,
        )

    class FakeDB:
        async def get(self, model, identifier):  # type: ignore[no-untyped-def]
            return SimpleNamespace(
                id=identifier,
                name="Vision provider",
            )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_vision",
        fake_invoke_vision,
    )

    result = await run_vision_test_graph(
        db=FakeDB(),
        actor_user_id="admin-1",
        image_bytes=b"png-bytes",
        content_type="image/png",
    )

    assert result["ok"] is True
    assert result["provider_kind"] == "openai"
    assert result["provider_name"] == "Vision provider"
    assert result["model"] == "gpt-4o"
    assert result["result_text"] == "Счет №42\nИтого: 15 000 ₽"
