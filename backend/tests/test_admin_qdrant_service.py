from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from qdrant_client import models

from app.core.database import AsyncSessionLocal
from app.models.change_proposal import ChangeProposal, ProposalStatus
from app.models.project import Project
from app.models.task import Task, TaskAttachment, TaskStatus
from app.models.user import User, UserRole
from app.models.validation_question import ValidationQuestion
from app.schemas.admin_qdrant import QdrantDuplicateProposalProbePayload
from app.services.admin_qdrant_service import AdminQdrantService
from app.services.qdrant_service import (
    PROJECT_QUESTIONS_COLLECTION,
    TASK_KNOWLEDGE_COLLECTION,
    QdrantService,
)


def make_collection_info(
    *,
    metadata: dict[str, str],
    points_count: int,
    vector_size: int,
) -> SimpleNamespace:
    return SimpleNamespace(
        status=models.CollectionStatus.GREEN,
        points_count=points_count,
        indexed_vectors_count=points_count,
        segments_count=1,
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE,
                )
            ),
            metadata=metadata,
        ),
    )


def test_task_filter_targets_metadata_task_id() -> None:
    filter_ = AdminQdrantService._task_filter("task-123")

    assert len(filter_.must) == 1
    assert filter_.must[0].key == "metadata.task_id"
    assert filter_.must[0].match.value == "task-123"


@pytest.mark.asyncio
async def test_get_overview_marks_empty_collections_and_metadata_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeClient:
        def get_collections(self) -> None:
            return None

        def collection_exists(self, collection_name: str) -> bool:
            return True

        def get_collection(self, collection_name: str) -> SimpleNamespace:
            if collection_name == "task_knowledge":
                return make_collection_info(
                    metadata={
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-large",
                    },
                    points_count=4,
                    vector_size=3072,
                )
            if collection_name == "project_questions":
                return make_collection_info(
                    metadata={
                        "embedding_provider": "openai",
                        "embedding_model": "text-embedding-3-small",
                    },
                    points_count=0,
                    vector_size=1536,
                )
            return make_collection_info(
                metadata={
                    "embedding_provider": "openai",
                    "embedding_model": "text-embedding-3-small",
                },
                points_count=2,
                vector_size=1536,
            )

    monkeypatch.setattr(
        QdrantService,
        "get_embedding_configuration",
        lambda: {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "vector_size": 1536,
            "qdrant_url": "http://localhost:6333",
        },
    )
    monkeypatch.setattr(QdrantService, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(
        QdrantService,
        "get_sample_payload_keys",
        lambda collection_name: ["task_id", "task_title"]
        if collection_name == "task_knowledge"
        else [],
    )

    overview = await AdminQdrantService.get_overview()

    assert overview.connected is True
    task_collection = next(
        item for item in overview.collections if item.collection_name == "task_knowledge"
    )
    assert task_collection.exists is True
    assert task_collection.vectors_count is None
    assert task_collection.indexed_vectors_count == 4
    assert task_collection.metadata_matches_active_embeddings is False
    assert any("Модель эмбеддингов" in warning for warning in task_collection.warnings)

    project_questions = next(
        item for item in overview.collections if item.collection_name == "project_questions"
    )
    assert project_questions.exists is True
    assert project_questions.points_count == 0
    assert any("не содержит точек" in warning for warning in project_questions.warnings)


@pytest.mark.asyncio
async def test_get_overview_handles_connection_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenClient:
        def get_collections(self) -> None:
            raise RuntimeError("Qdrant unavailable")

    monkeypatch.setattr(
        QdrantService,
        "get_embedding_configuration",
        lambda: {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "vector_size": 1536,
            "qdrant_url": "http://localhost:6333",
        },
    )
    monkeypatch.setattr(QdrantService, "_get_client", lambda: BrokenClient())

    overview = await AdminQdrantService.get_overview()

    assert overview.connected is False
    assert overview.connection_error == "Qdrant unavailable"
    assert all(item.error == "Qdrant unavailable" for item in overview.collections)


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_get_project_coverage_counts_live_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSessionLocal() as db:
        admin = User(
            email="coverage-admin@example.com",
            password_hash="hash",
            full_name="Coverage Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()

        project = Project(name="Coverage Project", description=None, created_by=admin.id)
        db.add(project)
        await db.flush()

        fresh_task = Task(
            project_id=project.id,
            title="Fresh task",
            content="Index me",
            tags=["backend"],
            status=TaskStatus.DRAFT,
            created_by=admin.id,
            analyst_id=admin.id,
            indexed_at=datetime.now(UTC),
        )
        stale_task = Task(
            project_id=project.id,
            title="Stale task",
            content="Reindex me",
            tags=["qa"],
            status=TaskStatus.NEEDS_REWORK,
            created_by=admin.id,
            analyst_id=admin.id,
            indexed_at=datetime(2026, 4, 20, tzinfo=UTC),
            updated_at=datetime(2026, 4, 21, tzinfo=UTC),
        )
        db.add_all([fresh_task, stale_task])
        await db.flush()

        db.add(
            ValidationQuestion(
                task_id=fresh_task.id,
                source="chat",
                question_text="Нужно ли добавить интеграционный тест?",
                validation_verdict="approved",
                sort_order=0,
            )
        )
        await db.commit()

        def fake_count_points(
            collection_name: str,
            *,
            filter_: models.Filter | None = None,
        ) -> int:
            assert filter_ is not None
            assert filter_.must[0].key == "metadata.task_id"
            task_id = str(filter_.must[0].match.value)
            counts = {
                (TASK_KNOWLEDGE_COLLECTION, fresh_task.id): 3,
                (PROJECT_QUESTIONS_COLLECTION, fresh_task.id): 1,
                (TASK_KNOWLEDGE_COLLECTION, stale_task.id): 0,
                (PROJECT_QUESTIONS_COLLECTION, stale_task.id): 0,
            }
            return counts.get((collection_name, task_id), 0)

        monkeypatch.setattr(QdrantService, "count_points", fake_count_points)

        coverage = await AdminQdrantService.get_project_coverage(project.id, db, limit=20)

        assert coverage.summary.tasks_total == 2
        assert coverage.summary.tasks_with_knowledge_total == 1
        assert coverage.summary.tasks_with_questions_total == 1
        assert coverage.items[0].knowledge_points_count in {0, 3}
        fresh_row = next(item for item in coverage.items if item.id == fresh_task.id)
        assert fresh_row.knowledge_points_count == 3
        assert fresh_row.question_points_count == 1
        assert fresh_row.validation_questions_total == 1


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_probe_duplicate_proposal_marks_near_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with AsyncSessionLocal() as db:
        admin = User(
            email="duplicate-admin@example.com",
            password_hash="hash",
            full_name="Duplicate Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()

        project = Project(name="Duplicates", description=None, created_by=admin.id)
        db.add(project)
        await db.flush()

        task = Task(
            project_id=project.id,
            title="Синхронизация статусов",
            content="Нужно синхронизировать статусы между системами.",
            tags=["integration"],
            status=TaskStatus.IN_PROGRESS,
            created_by=admin.id,
            analyst_id=admin.id,
        )
        db.add(task)
        await db.flush()

        proposal = ChangeProposal(
            task_id=task.id,
            proposal_text="Добавить двустороннюю синхронизацию статусов.",
            status=ProposalStatus.NEW,
        )
        db.add(proposal)
        await db.commit()

        monkeypatch.setattr(
            QdrantService,
            "probe_duplicate_proposals",
            AsyncMock(
                return_value=[
                    {
                        "proposal_id": proposal.id,
                        "task_id": task.id,
                        "status": "new",
                        "score": 0.9,
                        "proposal_text": proposal.proposal_text,
                    }
                ]
            ),
        )

        probe = await AdminQdrantService.probe_duplicate_proposal(
            QdrantDuplicateProposalProbePayload(
                project_id=project.id,
                proposal_text=proposal.proposal_text,
            ),
            db,
        )

        assert probe.heuristic_status == "warning"
        assert probe.raw_threshold == 0.92
        assert probe.results[0].match_band == "near_threshold"
        assert probe.results[0].task_title == "Синхронизация статусов"


@pytest.mark.asyncio
@pytest.mark.requires_db
async def test_resync_task_avoids_vision_and_reports_missing_alt_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "diagram.png"
    image_path.write_bytes(b"fake-image")

    async with AsyncSessionLocal() as db:
        admin = User(
            email="resync-admin@example.com",
            password_hash="hash",
            full_name="Resync Admin",
            role=UserRole.ADMIN,
        )
        db.add(admin)
        await db.flush()

        project = Project(name="Resync Project", description=None, created_by=admin.id)
        db.add(project)
        await db.flush()

        task = Task(
            project_id=project.id,
            title="Диагностика индекса",
            content="Нужно пересобрать индекс без vision-вызова.",
            tags=["ops"],
            status=TaskStatus.DRAFT,
            created_by=admin.id,
            analyst_id=admin.id,
            validation_result={"questions": [], "verdict": "approved", "issues": []},
        )
        db.add(task)
        await db.flush()

        attachment = TaskAttachment(
            task_id=task.id,
            filename="diagram.png",
            content_type="image/png",
            storage_path=str(image_path),
            alt_text=None,
        )
        db.add(attachment)
        await db.commit()

        async def fail_if_vision_called(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("Vision must not be called during Qdrant resync")

        async def fake_index_task_context(*args, **kwargs):  # type: ignore[no-untyped-def]
            assert kwargs["allow_vision"] is False
            indexed_task = args[1]
            indexed_task.indexed_at = datetime.now(UTC)
            return ["chunk-1"]

        monkeypatch.setattr(
            "app.services.attachment_content_service.AttachmentContentService.ensure_image_alt_text",
            fail_if_vision_called,
        )
        monkeypatch.setattr(
            "app.services.admin_qdrant_service.RagService.index_task_context",
            fake_index_task_context,
        )
        monkeypatch.setattr(
            "app.services.admin_qdrant_service.ValidationQuestionService.sync_project_questions_index",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            QdrantService,
            "count_points",
            lambda collection_name, *, filter_=None: 1
            if collection_name == TASK_KNOWLEDGE_COLLECTION
            else 0,
        )

        result = await AdminQdrantService.resync_task(task.id, admin, db)

        assert result.chunk_ids == ["chunk-1"]
        assert result.knowledge_points_count == 1
        assert any("alt-text" in warning for warning in result.warnings)
