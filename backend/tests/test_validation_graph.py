from __future__ import annotations

import pytest

from app.agents.validation_graph import run_validation_graph


@pytest.mark.asyncio
async def test_validation_graph_respects_disabled_nodes() -> None:
    result = await run_validation_graph(
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
