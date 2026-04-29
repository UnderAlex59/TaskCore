from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from app.models.task import Task, TaskStatus
from app.models.user import User, UserRole
from app.schemas.task import TaskApprove
from app.services.audit_service import AuditService
from app.services.chat_realtime import chat_connection_manager
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
    db.add = Mock()

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
    db.add = Mock()
    db.execute = AsyncMock(return_value=Mock(scalars=Mock(return_value=Mock(first=Mock(return_value=None)))))
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


@pytest.mark.asyncio
async def test_approve_task_keeps_status_awaiting_approval_until_second_reviewer_confirms(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task()
    task.status = TaskStatus.AWAITING_APPROVAL
    task.developer_id = None
    task.tester_id = None
    current_user = make_user()
    db = AsyncMock()
    db.add = Mock()
    db.execute = AsyncMock(
        return_value=Mock(scalars=Mock(return_value=Mock(first=Mock(return_value=None))))
    )
    serialized_task = object()

    monkeypatch.setattr(TaskService, "get_task_with_access", AsyncMock(return_value=task))
    monkeypatch.setattr(TaskService, "_get_project_member_or_422", AsyncMock())
    monkeypatch.setattr(TaskService, "_get_attachments", AsyncMock(return_value=[]))
    monkeypatch.setattr(TaskService, "_get_user_name", AsyncMock(return_value="Ira Reviewer"))
    monkeypatch.setattr(TaskService, "_broadcast_latest_agent_message", AsyncMock())
    monkeypatch.setattr(TaskService, "_serialize_task", Mock(return_value=serialized_task))
    monkeypatch.setattr(AuditService, "record", Mock())
    monkeypatch.setattr("app.services.task_service.serialize_message", Mock(return_value={}))
    monkeypatch.setattr(chat_connection_manager, "broadcast_messages", AsyncMock())

    result = await TaskService.approve_task(
        "task-1",
        TaskApprove(
            developer_id="developer-1",
            tester_id="tester-1",
            reviewer_analyst_id="reviewer-1",
        ),
        current_user,
        db,
    )

    assert result is serialized_task
    assert task.status == TaskStatus.AWAITING_APPROVAL
    assert task.developer_id == "developer-1"
    assert task.tester_id == "tester-1"
    assert task.reviewer_analyst_id == "reviewer-1"
    assert task.reviewer_approved_at is None
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_start_development_moves_task_into_in_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task()
    task.developer_id = "developer-1"
    current_user = User(
        id="developer-1",
        email="developer@example.com",
        password_hash="hashed",
        full_name="Dan Developer",
        role=UserRole.DEVELOPER,
    )
    db = AsyncMock()
    db.add = Mock()
    serialized_task = object()

    monkeypatch.setattr(TaskService, "get_task_with_access", AsyncMock(return_value=task))
    monkeypatch.setattr(TaskService, "_get_attachments", AsyncMock(return_value=[]))
    monkeypatch.setattr(TaskService, "_broadcast_latest_agent_message", AsyncMock())
    monkeypatch.setattr(TaskService, "_serialize_task", Mock(return_value=serialized_task))
    monkeypatch.setattr(AuditService, "record", Mock())

    result = await TaskService.start_development("task-1", current_user, db)

    assert result is serialized_task
    assert task.status == TaskStatus.IN_PROGRESS
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_mark_ready_for_testing_moves_task_into_ready_for_testing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = make_task()
    task.status = TaskStatus.IN_PROGRESS
    task.developer_id = "developer-1"
    current_user = User(
        id="developer-1",
        email="developer@example.com",
        password_hash="hashed",
        full_name="Dan Developer",
        role=UserRole.DEVELOPER,
    )
    db = AsyncMock()
    db.add = Mock()
    serialized_task = object()

    monkeypatch.setattr(TaskService, "get_task_with_access", AsyncMock(return_value=task))
    monkeypatch.setattr(TaskService, "_get_attachments", AsyncMock(return_value=[]))
    monkeypatch.setattr(TaskService, "_broadcast_latest_agent_message", AsyncMock())
    monkeypatch.setattr(TaskService, "_serialize_task", Mock(return_value=serialized_task))
    monkeypatch.setattr(AuditService, "record", Mock())

    result = await TaskService.mark_ready_for_testing("task-1", current_user, db)

    assert result is serialized_task
    assert task.status == TaskStatus.READY_FOR_TESTING
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(task)
