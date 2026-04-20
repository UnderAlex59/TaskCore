from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_core.documents import Document
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
}
_DUPLICATE_PROPOSAL_SCORE_THRESHOLD = 0.92


class QdrantService:
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
    @lru_cache
    def _get_embeddings() -> OpenAIEmbeddings:
        settings = get_settings()
        api_key = settings.OPENAI_API_KEY
        if not api_key and settings.OPENAI_BASE_URL:
            api_key = "local"
        if not api_key:
            raise RuntimeError("Embeddings provider is not configured")

        kwargs: dict[str, Any] = {
            "model": settings.EMBEDDING_MODEL,
            "api_key": api_key,
        }
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        return OpenAIEmbeddings(**kwargs)

    @staticmethod
    def _get_vector_size() -> int:
        settings = get_settings()
        if settings.EMBEDDING_DIMENSION is not None:
            return settings.EMBEDDING_DIMENSION

        vector_size = _VECTOR_SIZE_BY_MODEL.get(settings.EMBEDDING_MODEL)
        if vector_size is not None:
            return vector_size

        embeddings = QdrantService._get_embeddings()
        return len(embeddings.embed_query("dimension probe"))

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
                    continue
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE,
                    ),
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
                            models.FieldCondition(
                                key="task_id",
                                match=models.MatchValue(value=task_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )

            documents = [
                Document(
                    page_content=str(chunk.get("content", "")),
                    metadata={
                        "chunk_id": str(chunk["chunk_id"]),
                        "chunk_kind": str(chunk.get("chunk_kind", "task")),
                        "task_id": task_id,
                        "project_id": project_id,
                        "task_title": task_title,
                        "task_status": task_status,
                        "tags": list(tags),
                    },
                )
                for chunk in chunks
                if str(chunk.get("content", "")).strip()
            ]
            if not documents:
                return True

            await QdrantService._get_store(TASK_KNOWLEDGE_COLLECTION).aadd_documents(
                documents=documents,
                ids=[str(chunk["chunk_id"]) for chunk in chunks if str(chunk.get("content", "")).strip()],
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
                            models.FieldCondition(
                                key="task_id",
                                match=models.MatchValue(value=task_id),
                            )
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
                        models.FieldCondition(
                            key="task_id",
                            match=models.MatchValue(value=task_id),
                        )
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

            hits = await QdrantService._get_store(TASK_KNOWLEDGE_COLLECTION).asimilarity_search_with_score(
                query_text,
                k=max(limit * 6, 12),
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="project_id",
                            match=models.MatchValue(value=project_id),
                        )
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
                            models.FieldCondition(
                                key="task_id",
                                match=models.MatchValue(value=task_id),
                            )
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

            await QdrantService._get_store(PROJECT_QUESTIONS_COLLECTION).aadd_documents(
                documents=documents,
                ids=[str(item["question_id"]) for item in questions if str(item.get("question_text", "")).strip()],
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
                models.FieldCondition(
                    key="project_id",
                    match=models.MatchValue(value=project_id),
                )
            ]
            if tags:
                must_conditions.append(
                    models.FieldCondition(
                        key="tags",
                        match=models.MatchAny(any=tags),
                    )
                )

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
                            models.FieldCondition(
                                key="task_id",
                                match=models.MatchValue(value=task_id),
                            )
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

            hits = await QdrantService._get_store(TASK_PROPOSALS_COLLECTION).asimilarity_search_with_score(
                proposal_text,
                k=3,
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="project_id",
                            match=models.MatchValue(value=project_id),
                        ),
                        models.FieldCondition(
                            key="status",
                            match=models.MatchAny(any=["new", "accepted"]),
                        ),
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
                ids=[proposal_id],
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
                            models.FieldCondition(
                                key="task_id",
                                match=models.MatchValue(value=task_id),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception:
            logger.exception("Failed to delete proposal artifacts for task %s", task_id)
