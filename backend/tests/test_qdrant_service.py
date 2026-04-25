from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from qdrant_client import models

from app.services.qdrant_service import QdrantService

REAL_REPLACE_TASK_KNOWLEDGE = QdrantService.replace_task_knowledge


def make_settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "EMBEDDING_PROVIDER": None,
        "OPENAI_API_KEY": None,
        "OPENAI_BASE_URL": None,
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "OLLAMA_EMBEDDING_MODEL": "nomic-embed-text",
        "OLLAMA_BASE_URL": "http://ollama:11434",
        "EMBEDDING_DIMENSION": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def clear_embedding_caches() -> None:
    QdrantService._get_embeddings.cache_clear()


def test_explicit_openai_embeddings_use_openai_provider(monkeypatch) -> None:
    clear_embedding_caches()
    monkeypatch.setattr(
        "app.services.qdrant_service.get_settings",
        lambda: make_settings(
            EMBEDDING_PROVIDER="openai",
            OPENAI_API_KEY="test-key",
        ),
    )
    openai_embeddings = Mock(return_value="openai")
    ollama_embeddings = Mock(return_value="ollama")
    monkeypatch.setattr(QdrantService, "_get_openai_embeddings", openai_embeddings)
    monkeypatch.setattr(QdrantService, "_get_ollama_embeddings", ollama_embeddings)

    result = QdrantService._get_embeddings()

    assert result == "openai"
    openai_embeddings.assert_called_once_with()
    ollama_embeddings.assert_not_called()


def test_explicit_ollama_embeddings_use_ollama_provider(monkeypatch) -> None:
    clear_embedding_caches()
    monkeypatch.setattr(
        "app.services.qdrant_service.get_settings",
        lambda: make_settings(EMBEDDING_PROVIDER="ollama"),
    )
    openai_embeddings = Mock(return_value="openai")
    ollama_embeddings = Mock(return_value="ollama")
    monkeypatch.setattr(QdrantService, "_get_openai_embeddings", openai_embeddings)
    monkeypatch.setattr(QdrantService, "_get_ollama_embeddings", ollama_embeddings)

    result = QdrantService._get_embeddings()

    assert result == "ollama"
    openai_embeddings.assert_not_called()
    ollama_embeddings.assert_called_once_with()


def test_missing_embedding_provider_raises_clear_error(monkeypatch) -> None:
    clear_embedding_caches()
    monkeypatch.setattr(
        "app.services.qdrant_service.get_settings",
        lambda: make_settings(),
    )

    with pytest.raises(RuntimeError, match="EMBEDDING_PROVIDER"):
        QdrantService._get_embeddings()


def test_vector_size_uses_ollama_model_mapping(monkeypatch) -> None:
    clear_embedding_caches()
    monkeypatch.setattr(
        "app.services.qdrant_service.get_settings",
        lambda: make_settings(EMBEDDING_PROVIDER="ollama"),
    )

    assert QdrantService._get_vector_size() == 768


def test_embedding_metadata_uses_active_provider_and_model(monkeypatch) -> None:
    monkeypatch.setattr(QdrantService, "_resolve_embedding_provider", Mock(return_value="ollama"))
    monkeypatch.setattr(QdrantService, "_get_active_embedding_model", Mock(return_value="nomic-embed-text"))

    assert QdrantService._get_embedding_metadata() == {
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
    }


def test_collection_matches_active_embeddings_requires_matching_size_and_metadata(
    monkeypatch,
) -> None:
    monkeypatch.setattr(QdrantService, "_resolve_embedding_provider", Mock(return_value="ollama"))
    monkeypatch.setattr(QdrantService, "_get_active_embedding_model", Mock(return_value="nomic-embed-text"))
    collection_info = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=models.VectorParams(
                    size=768,
                    distance=models.Distance.COSINE,
                )
            ),
            metadata={
                "embedding_provider": "ollama",
                "embedding_model": "nomic-embed-text",
            },
        )
    )

    assert (
        QdrantService._collection_matches_active_embeddings(
            collection_info,
            expected_vector_size=768,
        )
        is True
    )
    assert (
        QdrantService._collection_matches_active_embeddings(
            collection_info,
            expected_vector_size=1536,
        )
        is False
    )

    collection_info.config.metadata["embedding_model"] = "text-embedding-3-small"
    assert (
        QdrantService._collection_matches_active_embeddings(
            collection_info,
            expected_vector_size=768,
        )
        is False
    )


def test_create_collection_writes_embedding_metadata(monkeypatch) -> None:
    client = Mock()
    monkeypatch.setattr(QdrantService, "_resolve_embedding_provider", Mock(return_value="ollama"))
    monkeypatch.setattr(QdrantService, "_get_active_embedding_model", Mock(return_value="nomic-embed-text"))

    QdrantService._create_collection(
        client,
        collection_name="task_knowledge",
        vector_size=768,
    )

    client.create_collection.assert_called_once()
    assert client.create_collection.call_args.kwargs["metadata"] == {
        "embedding_provider": "ollama",
        "embedding_model": "nomic-embed-text",
    }


def test_normalize_point_id_preserves_uuid_values() -> None:
    raw_id = "f1248baf-ee60-4867-bf43-d0e614b19717"

    normalized = QdrantService._normalize_point_id("task_knowledge", raw_id)

    assert normalized == raw_id


def test_normalize_point_id_hashes_invalid_string_values_to_uuid() -> None:
    raw_id = "f1248baf-ee60-4867-bf43-d0e614b19717:task_title:f1248baf-ee60-4867-bf43-d0e614b19717:0"

    normalized = QdrantService._normalize_point_id("task_knowledge", raw_id)

    assert normalized != raw_id
    assert normalized == QdrantService._normalize_point_id("task_knowledge", raw_id)
    assert str(uuid.UUID(str(normalized))) == normalized


@pytest.mark.asyncio
async def test_replace_task_knowledge_uses_normalized_point_ids(monkeypatch) -> None:
    client = Mock()

    class FakeStore:
        def __init__(self) -> None:
            self.ids: list[int | str] | None = None

        async def aadd_documents(self, *, documents, ids):  # type: ignore[no-untyped-def]
            self.ids = ids
            return None

    store = FakeStore()
    monkeypatch.setattr(QdrantService, "ensure_collections", AsyncMock(return_value=True))
    monkeypatch.setattr(QdrantService, "_get_client", Mock(return_value=client))
    monkeypatch.setattr(QdrantService, "_get_store", Mock(return_value=store))

    indexed = await REAL_REPLACE_TASK_KNOWLEDGE(
        task_id="f1248baf-ee60-4867-bf43-d0e614b19717",
        project_id="eb5e7f62-0930-4364-a3f8-ace96ee6a690",
        task_title="Commit indexing",
        task_status="ready_for_dev",
        tags=["backend"],
        chunks=[
            {
                "chunk_id": "f1248baf-ee60-4867-bf43-d0e614b19717:task_title:f1248baf-ee60-4867-bf43-d0e614b19717:0",
                "chunk_index": 0,
                "chunk_kind": "task",
                "content": "Index this task",
                "source_id": "f1248baf-ee60-4867-bf43-d0e614b19717",
                "source_total_chunks": 1,
                "source_type": "task_title",
            }
        ],
    )

    assert indexed is True
    ids = store.ids
    assert ids is not None
    assert len(ids) == 1
    assert ids[0] != "f1248baf-ee60-4867-bf43-d0e614b19717:task_title:f1248baf-ee60-4867-bf43-d0e614b19717:0"
    assert str(uuid.UUID(str(ids[0]))) == str(ids[0])
