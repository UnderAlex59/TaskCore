from __future__ import annotations

from app.services.llm_agent_registry import list_llm_agents


def test_list_llm_agents_includes_rag_vision() -> None:
    agents = {item.key: item for item in list_llm_agents()}

    assert "rag-vision" in agents
    assert agents["rag-vision"].name == "AttachmentVisionAgent"
    assert "vision-alt-text" in agents["rag-vision"].aliases


def test_list_llm_agents_includes_task_tag_suggester() -> None:
    agents = {item.key: item for item in list_llm_agents()}

    assert "task_tag_suggester" in agents
    assert agents["task_tag_suggester"].name == "TaskTagSuggester"
    assert "tag-suggester" in agents["task_tag_suggester"].aliases
