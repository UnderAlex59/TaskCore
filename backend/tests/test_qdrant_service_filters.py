from __future__ import annotations

from app.services.qdrant_service import QdrantService


def test_metadata_value_condition_uses_nested_metadata_key() -> None:
    condition = QdrantService._metadata_value_condition("project_id", "project-123")

    assert condition.key == "metadata.project_id"
    assert condition.match.value == "project-123"


def test_metadata_any_condition_uses_nested_metadata_key() -> None:
    condition = QdrantService._metadata_any_condition("status", ["new", "accepted"])

    assert condition.key == "metadata.status"
    assert condition.match.any == ["new", "accepted"]
