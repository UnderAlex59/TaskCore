from __future__ import annotations

import logging
import uuid
from functools import lru_cache
from typing import Any, Literal

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_ollama import OllamaEmbeddings
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from app.core.config import get_settings

logger = logging.getLogger(__name__)

PROJECT_QUESTIONS_COLLECTION = "project_questions"
TASK_KNOWLEDGE_COLLECTION = "task_knowledge"
TASK_PROPOSALS_COLLECTION = "task_proposals"

_VECTOR_SIZE_BY_MODEL = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
}
_DUPLICATE_PROPOSAL_SCORE_THRESHOLD = 0.92
_POINT_ID_NAMESPACE = uuid.UUID("a1fc4b4f-8c2d-4dcb-8a77-0f7a52465b62")


class QdrantService:
    @staticmethod
    def _metadata_key(field_name: str) -> str:
        return f"metadata.{field_name}"

    @staticmethod
    def _metadata_value_condition(key: str, value: str) -> models.FieldCondition:
        return models.FieldCondition(
            key=QdrantService._metadata_key(key),
            match=models.MatchValue(value=value),
        )

    @staticmethod
    def _metadata_any_condition(key: str, values: list[str]) -> models.FieldCondition:
        return models.FieldCondition(
            key=QdrantService._metadata_key(key),
            match=models.MatchAny(any=values),
        )

    @staticmethod
    def get_collection_names() -> tuple[str, str, str]:
        return (
            PROJECT_QUESTIONS_COLLECTION,
            TASK_KNOWLEDGE_COLLECTION,
            TASK_PROPOSALS_COLLECTION,
        )

    @staticmethod
    def get_duplicate_proposal_threshold() -> float:
        return _DUPLICATE_PROPOSAL_SCORE_THRESHOLD

    @staticmethod
    def _normalize_point_id(collection_name: str, raw_id: object) -> int | str:
        if isinstance(raw_id, bool):
            raw_id = str(raw_id)
        if isinstance(raw_id, int) and raw_id >= 0:
            return raw_id

        text = str(raw_id).strip()
        if not text:
            return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{collection_name}:<empty>"))

        try:
            return str(uuid.UUID(text))
        except ValueError:
            pass

        if text.isascii() and text.isdigit():
            numeric_id = int(text)
            if numeric_id >= 0:
                return numeric_id

        return str(uuid.uuid5(_POINT_ID_NAMESPACE, f"{collection_name}:{text}"))

    @staticmethod
    @lru_cache
    def _get_client() -> QdrantClient:
        settings = get_settings()
        return QdrantClient(
            url=settings.QDRANT_URL,
            api_key=settings.QDRANT_API_KEY,
            timeout=5.0,
        )

    @staticmethod
    def _resolve_embedding_provider() -> Literal["openai", "ollama"]:
        settings = get_settings()
        provider = settings.EMBEDDING_PROVIDER
        if provider is None:
            raise RuntimeError("EMBEDDING_PROVIDER must be explicitly configured in .env")
        provider = provider.casefold()
        if provider in {"openai", "ollama"}:
            return provider
        raise RuntimeError(f"Unsupported embedding provider: {settings.EMBEDDING_PROVIDER!r}")

    @staticmethod
    def _get_openai_embeddings() -> OpenAIEmbeddings:
        settings = get_settings()
        model = settings.EMBEDDING_MODEL
        if not model:
            raise RuntimeError("EMBEDDING_MODEL must be configured in .env for OpenAI embeddings")
        api_key = settings.OPENAI_API_KEY
        if not api_key and settings.OPENAI_BASE_URL:
            api_key = "local"
        if not api_key:
            raise RuntimeError("OpenAI embeddings provider is not configured")

        kwargs: dict[str, Any] = {
            "model": model,
            "api_key": api_key,
        }
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        return OpenAIEmbeddings(**kwargs)

    @staticmethod
    def _get_ollama_embeddings() -> OllamaEmbeddings:
        settings = get_settings()
        model = settings.OLLAMA_EMBEDDING_MODEL
        if not model:
            raise RuntimeError(
                "OLLAMA_EMBEDDING_MODEL must be configured in .env for Ollama embeddings"
            )
        return OllamaEmbeddings(
            model=model,
            base_url=settings.OLLAMA_BASE_URL,
        )

    @staticmethod
    def _get_active_embedding_model() -> str:
        settings = get_settings()
        provider = QdrantService._resolve_embedding_provider()
        if provider == "ollama":
            if not settings.OLLAMA_EMBEDDING_MODEL:
                raise RuntimeError(
                    "OLLAMA_EMBEDDING_MODEL must be configured in .env for Ollama embeddings"
                )
            return settings.OLLAMA_EMBEDDING_MODEL
        if not settings.EMBEDDING_MODEL:
            raise RuntimeError("EMBEDDING_MODEL must be configured in .env for OpenAI embeddings")
        return settings.EMBEDDING_MODEL

    @staticmethod
    def _get_embedding_metadata() -> dict[str, str]:
        provider = QdrantService._resolve_embedding_provider()
        return {
            "embedding_provider": provider,
            "embedding_model": QdrantService._get_active_embedding_model(),
        }

    @staticmethod
    @lru_cache
    def _get_embeddings() -> Embeddings:
        provider = QdrantService._resolve_embedding_provider()
        model_name = QdrantService._get_active_embedding_model()
        logger.info("Using %s embeddings model %s", provider, model_name)
        if provider == "ollama":
            return QdrantService._get_ollama_embeddings()
        return QdrantService._get_openai_embeddings()

    @staticmethod
    def _get_vector_size() -> int:
        settings = get_settings()
        if settings.EMBEDDING_DIMENSION is not None:
            return settings.EMBEDDING_DIMENSION

        vector_size = _VECTOR_SIZE_BY_MODEL.get(QdrantService._get_active_embedding_model())
        if vector_size is not None:
            return vector_size

        embeddings = QdrantService._get_embeddings()
        return len(embeddings.embed_query("dimension probe"))

    @staticmethod
    def get_embedding_configuration() -> dict[str, object | None]:
        settings = get_settings()
        provider = settings.EMBEDDING_PROVIDER.casefold() if settings.EMBEDDING_PROVIDER else None
        model: str | None
        if provider == "ollama":
            model = settings.OLLAMA_EMBEDDING_MODEL
        elif provider == "openai":
            model = settings.EMBEDDING_MODEL
        else:
            model = None

        vector_size = settings.EMBEDDING_DIMENSION
        if vector_size is None and model:
            vector_size = _VECTOR_SIZE_BY_MODEL.get(model)

        return {
            "provider": provider,
            "model": model,
            "vector_size": vector_size,
            "qdrant_url": settings.QDRANT_URL,
        }

    @staticmethod
    def _extract_vector_size(collection_info: models.CollectionInfo) -> int | None:
        vectors = collection_info.config.params.vectors
        if isinstance(vectors, models.VectorParams):
            return int(vectors.size)
        if isinstance(vectors, dict):
            for vector_params in vectors.values():
                if isinstance(vector_params, models.VectorParams):
                    return int(vector_params.size)
        return None

    @staticmethod
    def _collection_matches_active_embeddings(
        collection_info: models.CollectionInfo,
        *,
        expected_vector_size: int,
    ) -> bool:
        metadata = collection_info.config.metadata or {}
        expected_metadata = QdrantService._get_embedding_metadata()
        return (
            QdrantService._extract_vector_size(collection_info) == expected_vector_size
            and metadata.get("embedding_provider") == expected_metadata["embedding_provider"]
            and metadata.get("embedding_model") == expected_metadata["embedding_model"]
        )

    @staticmethod
    def _create_collection(
        client: QdrantClient,
        *,
        collection_name: str,
        vector_size: int,
    ) -> None:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
            metadata=QdrantService._get_embedding_metadata(),
        )

    @staticmethod
    def _get_store(collection_name: str) -> QdrantVectorStore:
        return QdrantVectorStore(
            client=QdrantService._get_client(),
            collection_name=collection_name,
            embedding=QdrantService._get_embeddings(),
        )

    @staticmethod
    def _filter_selector(filter_: models.Filter) -> models.FilterSelector:
        return models.FilterSelector(filter=filter_)

    @staticmethod
    def count_points(
        collection_name: str,
        *,
        filter_: models.Filter | None = None,
    ) -> int:
        result = QdrantService._get_client().count(
            collection_name=collection_name,
            count_filter=filter_,
        )
        return int(result.count)

    @staticmethod
    def get_sample_payload_keys(
        collection_name: str,
        *,
        filter_: models.Filter | None = None,
    ) -> list[str]:
        points, _ = QdrantService._get_client().scroll(
            collection_name=collection_name,
            scroll_filter=filter_,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return []

        payload = points[0].payload or {}
        return sorted(str(key) for key in payload)

    @staticmethod
    async def ensure_collections() -> bool:
        try:
            client = QdrantService._get_client()
            vector_size = QdrantService._get_vector_size()
            collections = (
                PROJECT_QUESTIONS_COLLECTION,
                TASK_KNOWLEDGE_COLLECTION,
                TASK_PROPOSALS_COLLECTION,
            )

            for collection_name in collections:
                if client.collection_exists(collection_name):
                    collection_info = client.get_collection(collection_name)
                    if QdrantService._collection_matches_active_embeddings(
                        collection_info,
                        expected_vector_size=vector_size,
                    ):
                        continue
                    logger.warning(
                        "Recreating Qdrant collection %s due to embedding configuration change",
                        collection_name,
                    )
                    client.delete_collection(collection_name=collection_name)
                QdrantService._create_collection(
                    client,
                    collection_name=collection_name,
                    vector_size=vector_size,
                )
            return True
        except Exception:
            logger.exception("Failed to initialize Qdrant collections")
            return False

    @staticmethod
    async def replace_task_knowledge(
        *,
        task_id: str,
        project_id: str,
        task_title: str,
        task_status: str,
        tags: list[str],
        chunks: list[dict[str, Any]],
    ) -> bool:
        if not chunks:
            return await QdrantService.delete_task_knowledge(task_id=task_id)

        try:
            if not await QdrantService.ensure_collections():
                return False

            client = QdrantService._get_client()
            client.delete(
                collection_name=TASK_KNOWLEDGE_COLLECTION,
                points_selector=QdrantService._filter_selector(
                    models.Filter(
                        must=[
                            QdrantService._metadata_value_condition("task_id", task_id)
                        ]
                    )
                ),
                wait=True,
            )

            documents: list[Document] = []
            ids: list[int | str] = []
            for chunk in chunks:
                content = str(chunk.get("content", "")).strip()
                if not content:
                    continue

                metadata: dict[str, Any] = {
                    "chunk_id": str(chunk["chunk_id"]),
                    "chunk_index": int(chunk.get("chunk_index", 0)),
                    "chunk_kind": str(chunk.get("chunk_kind", "task")),
                    "project_id": project_id,
                    "source_id": str(chunk.get("source_id", task_id)),
                    "source_total_chunks": int(chunk.get("source_total_chunks", 1)),
                    "source_type": str(chunk.get("source_type", chunk.get("chunk_kind", "task"))),
                    "tags": list(tags),
                    "task_id": task_id,
                    "task_status": task_status,
                    "task_title": task_title,
                }
                if chunk.get("filename") is not None:
                    metadata["filename"] = str(chunk["filename"])

                documents.append(Document(page_content=content, metadata=metadata))
                ids.append(
                    QdrantService._normalize_point_id(
                        TASK_KNOWLEDGE_COLLECTION,
                        chunk["chunk_id"],
                    )
                )
            if not documents:
                return True

            await QdrantService._get_store(TASK_KNOWLEDGE_COLLECTION).aadd_documents(
                documents=documents,
                ids=ids,
            )
            return True
        except Exception:
            logger.exception("Failed to index task knowledge for task %s", task_id)
            return False

    @staticmethod
    async def delete_task_knowledge(*, task_id: str) -> bool:
        try:
            client = QdrantService._get_client()
            client.delete(
                collection_name=TASK_KNOWLEDGE_COLLECTION,
                points_selector=QdrantService._filter_selector(
                    models.Filter(
                        must=[
                            QdrantService._metadata_value_condition("task_id", task_id)
                        ]
                    )
                ),
                wait=True,
            )
            return True
        except Exception:
            logger.exception("Failed to delete task knowledge for task %s", task_id)
            return False

    @staticmethod
    async def search_task_knowledge(
        *,
        task_id: str,
        query_text: str,
        limit: int = 4,
    ) -> list[Document]:
        try:
            if not await QdrantService.ensure_collections():
                return []

            return await QdrantService._get_store(TASK_KNOWLEDGE_COLLECTION).asimilarity_search(
                query_text,
                k=limit,
                filter=models.Filter(
                    must=[
                        QdrantService._metadata_value_condition("task_id", task_id)
                    ]
                ),
            )
        except Exception:
            logger.exception("Failed to search task knowledge for task %s", task_id)
            return []

    @staticmethod
    async def search_related_tasks(
        *,
        project_id: str,
        query_text: str,
        exclude_task_id: str | None = None,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        try:
            if not await QdrantService.ensure_collections():
                return []

            store = QdrantService._get_store(TASK_KNOWLEDGE_COLLECTION)
            hits = await store.asimilarity_search_with_score(
                query_text,
                k=max(limit * 6, 12),
                filter=models.Filter(
                    must=[
                        QdrantService._metadata_value_condition("project_id", project_id)
                    ]
                ),
            )

            ranked_by_task: dict[str, dict[str, object]] = {}
            for document, score in hits:
                task_id = str(document.metadata.get("task_id", "")).strip()
                if not task_id or task_id == exclude_task_id:
                    continue

                existing = ranked_by_task.get(task_id)
                if existing is not None and float(existing["score"]) >= float(score):
                    continue

                ranked_by_task[task_id] = {
                    "task_id": task_id,
                    "title": str(document.metadata.get("task_title", task_id)),
                    "status": str(document.metadata.get("task_status", "")),
                    "score": round(float(score), 4),
                }

            return sorted(
                ranked_by_task.values(),
                key=lambda item: float(item["score"]),
                reverse=True,
            )[:limit]
        except Exception:
            logger.exception("Failed to search related tasks for project %s", project_id)
            return []

    @staticmethod
    async def replace_project_questions(
        *,
        task_id: str,
        project_id: str,
        tags: list[str],
        questions: list[dict[str, Any]],
    ) -> bool:
        try:
            if not await QdrantService.ensure_collections():
                return False

            client = QdrantService._get_client()
            client.delete(
                collection_name=PROJECT_QUESTIONS_COLLECTION,
                points_selector=QdrantService._filter_selector(
                    models.Filter(
                        must=[
                            QdrantService._metadata_value_condition("task_id", task_id)
                        ]
                    )
                ),
                wait=True,
            )

            documents = [
                Document(
                    page_content=str(item["question_text"]),
                    metadata={
                        "question_id": str(item["question_id"]),
                        "task_id": task_id,
                        "project_id": project_id,
                        "tags": list(tags),
                        "validation_verdict": str(item.get("validation_verdict") or ""),
                    },
                )
                for item in questions
                if str(item.get("question_text", "")).strip()
            ]
            if not documents:
                return True

            ids = [
                QdrantService._normalize_point_id(
                    PROJECT_QUESTIONS_COLLECTION,
                    item["question_id"],
                )
                for item in questions
                if str(item.get("question_text", "")).strip()
            ]
            await QdrantService._get_store(PROJECT_QUESTIONS_COLLECTION).aadd_documents(
                documents=documents,
                ids=ids,
            )
            return True
        except Exception:
            logger.exception("Failed to sync project questions for task %s", task_id)
            return False

    @staticmethod
    async def search_project_questions(
        *,
        project_id: str,
        query_text: str,
        tags: list[str],
        limit: int = 5,
    ) -> list[Document]:
        try:
            if not await QdrantService.ensure_collections():
                return []

            must_conditions: list[models.FieldCondition] = [
                QdrantService._metadata_value_condition("project_id", project_id)
            ]
            if tags:
                must_conditions.append(QdrantService._metadata_any_condition("tags", tags))

            return await QdrantService._get_store(PROJECT_QUESTIONS_COLLECTION).asimilarity_search(
                query_text,
                k=limit,
                filter=models.Filter(must=must_conditions),
            )
        except Exception:
            logger.exception("Failed to search project questions for project %s", project_id)
            return []

    @staticmethod
    async def delete_project_questions_for_task(*, task_id: str) -> bool:
        try:
            client = QdrantService._get_client()
            client.delete(
                collection_name=PROJECT_QUESTIONS_COLLECTION,
                points_selector=QdrantService._filter_selector(
                    models.Filter(
                        must=[
                            QdrantService._metadata_value_condition("task_id", task_id)
                        ]
                    )
                ),
                wait=True,
            )
            return True
        except Exception:
            logger.exception("Failed to delete project questions for task %s", task_id)
            return False

    @staticmethod
    async def find_duplicate_proposal(
        *,
        project_id: str,
        proposal_text: str,
    ) -> dict[str, object] | None:
        try:
            if not await QdrantService.ensure_collections():
                return None

            store = QdrantService._get_store(TASK_PROPOSALS_COLLECTION)
            hits = await store.asimilarity_search_with_score(
                proposal_text,
                k=3,
                filter=models.Filter(
                    must=[
                        QdrantService._metadata_value_condition("project_id", project_id),
                        QdrantService._metadata_any_condition("status", ["new", "accepted"]),
                    ]
                ),
            )
            if not hits:
                return None

            document, score = hits[0]
            if float(score) < _DUPLICATE_PROPOSAL_SCORE_THRESHOLD:
                return None

            return {
                "proposal_id": document.metadata.get("proposal_id"),
                "task_id": document.metadata.get("task_id"),
                "score": round(float(score), 4),
                "proposal_text": document.page_content,
            }
        except Exception:
            logger.exception("Failed to search duplicate proposal in project %s", project_id)
            return None

    @staticmethod
    async def probe_duplicate_proposals(
        *,
        project_id: str,
        proposal_text: str,
        limit: int = 3,
    ) -> list[dict[str, object]]:
        try:
            if not await QdrantService.ensure_collections():
                return []

            store = QdrantService._get_store(TASK_PROPOSALS_COLLECTION)
            hits = await store.asimilarity_search_with_score(
                proposal_text,
                k=limit,
                filter=models.Filter(
                    must=[
                        QdrantService._metadata_value_condition("project_id", project_id),
                        QdrantService._metadata_any_condition("status", ["new", "accepted"]),
                    ]
                ),
            )
            return [
                {
                    "proposal_id": document.metadata.get("proposal_id"),
                    "task_id": document.metadata.get("task_id"),
                    "status": document.metadata.get("status"),
                    "score": round(float(score), 4),
                    "proposal_text": document.page_content,
                }
                for document, score in hits
            ]
        except Exception:
            logger.exception("Failed to probe duplicate proposals in project %s", project_id)
            return []

    @staticmethod
    async def upsert_proposal(
        *,
        proposal_id: str,
        task_id: str,
        project_id: str,
        proposal_text: str,
        status: str,
    ) -> bool:
        try:
            if not await QdrantService.ensure_collections():
                return False

            await QdrantService._get_store(TASK_PROPOSALS_COLLECTION).aadd_documents(
                documents=[
                    Document(
                        page_content=proposal_text,
                        metadata={
                            "proposal_id": proposal_id,
                            "task_id": task_id,
                            "project_id": project_id,
                            "status": status,
                        },
                    )
                ],
                ids=[
                    QdrantService._normalize_point_id(
                        TASK_PROPOSALS_COLLECTION,
                        proposal_id,
                    )
                ],
            )
            return True
        except Exception:
            logger.exception("Failed to index proposal %s", proposal_id)
            return False

    @staticmethod
    async def delete_task_artifacts(*, task_id: str) -> None:
        await QdrantService.delete_task_knowledge(task_id=task_id)
        await QdrantService.delete_project_questions_for_task(task_id=task_id)
        try:
            client = QdrantService._get_client()
            client.delete(
                collection_name=TASK_PROPOSALS_COLLECTION,
                points_selector=QdrantService._filter_selector(
                    models.Filter(
                        must=[
                            QdrantService._metadata_value_condition("task_id", task_id)
                        ]
                    )
                ),
                wait=True,
            )
        except Exception:
            logger.exception("Failed to delete proposal artifacts for task %s", task_id)
