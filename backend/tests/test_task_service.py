from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.services.audit_service import AuditService
from app.services.project_service import ProjectService
from app.services.rag_service import RagService
from app.services.task_service import TaskService


def make_task() -> Task:
    task = Task(
        id="task-1",
        project_id="project-1",
        title="Shared delivery notes",
        content="Current task body",
        tags=["delivery"],
        status=TaskStatus.READY_FOR_DEV,
        created_by="analyst-1",
        analyst_id="analyst-1",
    )
    task.updated_at = datetime(2026, 4, 23, tzinfo=UTC)
    task.indexed_at = None
    return task


def make_user() -> User:
    return User(
        id="analyst-1",
        email="analyst@example.com",
        password_hash="hashed",
        full_name="Nina Analyst",
        role=UserRole.ANALYST,
    )


@pytest.mark.asyncio
async def test_commit_task_changes_raises_when_indexing_did_not_publish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task()
    current_user = make_user()
    db = AsyncMock()

    monkeypatch.setattr(ProjectService, "ensure_project_access", AsyncMock())
    monkeypatch.setattr(TaskService, "get_task_or_404", AsyncMock(return_value=task))
    monkeypatch.setattr(TaskService, "_get_attachments", AsyncMock(return_value=[]))

    async def fake_index_task_context(*args, **kwargs) -> list[str]:
        task.indexed_at = None
        return []

    monkeypatch.setattr(RagService, "index_task_context", fake_index_task_context)
    audit_record = Mock()
    monkeypatch.setattr(AuditService, "record", audit_record)

    with pytest.raises(HTTPException) as exc_info:
        await TaskService.commit_task_changes("project-1", "task-1", current_user, db)

    assert exc_info.value.status_code == 503
    assert "индекс" in exc_info.value.detail.lower()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()
    audit_record.assert_not_called()


@pytest.mark.asyncio
async def test_commit_task_changes_returns_serialized_task_when_indexing_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task()
    current_user = make_user()
    db = AsyncMock()
    serialized_task = object()

    monkeypatch.setattr(ProjectService, "ensure_project_access", AsyncMock())
    monkeypatch.setattr(TaskService, "get_task_or_404", AsyncMock(return_value=task))
    monkeypatch.setattr(TaskService, "_get_attachments", AsyncMock(return_value=[]))

    async def fake_index_task_context(*args, **kwargs) -> list[str]:
        task.indexed_at = datetime.now(UTC)
        return ["chunk-1"]

    monkeypatch.setattr(RagService, "index_task_context", fake_index_task_context)
    audit_record = Mock()
    monkeypatch.setattr(AuditService, "record", audit_record)
    serialize_task = Mock(return_value=serialized_task)
    monkeypatch.setattr(TaskService, "_serialize_task", serialize_task)

    result = await TaskService.commit_task_changes("project-1", "task-1", current_user, db)

    assert result is serialized_task
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(task)
    audit_record.assert_called_once()
    serialize_task.assert_called_once_with(task, [])
