from __future__ import annotations

from pathlib import Path

from langchain_core.runnables.graph import Graph

from app.agents.chat_graph import get_chat_graph
from app.agents.graph_export import export_agent_graph_images
from app.agents.rag_pipeline import get_rag_pipeline_graph
from app.agents.validation_graph import get_validation_graph


def test_compiled_langgraph_shapes_are_exportable() -> None:
    chat_mermaid = get_chat_graph().get_graph().draw_mermaid()
    validation_mermaid = get_validation_graph().get_graph().draw_mermaid()
    rag_mermaid = get_rag_pipeline_graph().get_graph().draw_mermaid()

    assert "prepare_chat_request" in chat_mermaid
    assert "evaluate_core_rules" in validation_mermaid
    assert "collect_base_chunks" in rag_mermaid


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
        "validation_graph.png",
        "rag_pipeline.png",
    }
    for path in exported_paths:
        assert path.exists()
        assert path.read_bytes() == b"fake-png"
