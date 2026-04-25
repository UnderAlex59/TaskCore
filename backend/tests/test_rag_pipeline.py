from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.rag_pipeline import run_rag_pipeline, split_text_for_rag
from app.services.attachment_content_service import AttachmentContentService
from app.services.llm_runtime_service import LLMInvocationResult
from app.services.rag_service import RagService


class FakeDB:
    def __init__(self) -> None:
        self.flushed = False

    async def flush(self) -> None:
        self.flushed = True


def test_split_text_for_rag_keeps_short_text_as_single_chunk() -> None:
    assert split_text_for_rag(
        "короткое описание задачи",
        target_tokens=10,
        overlap_tokens=2,
    ) == ["короткое описание задачи"]


def test_split_text_for_rag_splits_long_text_with_overlap() -> None:
    text = " ".join(f"token{i}" for i in range(12))
    chunks = split_text_for_rag(text, target_tokens=5, overlap_tokens=2)

    assert chunks == [
        "token0 token1 token2 token3 token4",
        "token3 token4 token5 token6 token7",
        "token6 token7 token8 token9 token10",
        "token9 token10 token11",
    ]


def test_split_text_for_rag_drops_empty_chunks() -> None:
    assert split_text_for_rag(" \n\t ", target_tokens=5, overlap_tokens=1) == []


def test_attachment_text_extraction_supports_utf8_and_cp1251(tmp_path) -> None:
    utf8_path = tmp_path / "note.txt"
    utf8_path.write_text("Русский текст в UTF-8", encoding="utf-8")
    cp1251_path = tmp_path / "legacy.txt"
    cp1251_path.write_bytes("Русский текст в CP1251".encode("cp1251"))

    assert AttachmentContentService.extract_text(utf8_path, "text/plain") == "Русский текст в UTF-8"
    assert (
        AttachmentContentService.extract_text(cp1251_path, "text/plain") == "Русский текст в CP1251"
    )


def test_attachment_text_extraction_ignores_unsupported_types(tmp_path) -> None:
    archive_path = tmp_path / "archive.bin"
    archive_path.write_bytes(b"opaque")

    assert AttachmentContentService.extract_text(archive_path, "application/octet-stream") is None


@pytest.mark.asyncio
async def test_image_attachment_generates_alt_text(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    image_path = tmp_path / "mockup.png"
    image_path.write_bytes(b"fake image")
    db = FakeDB()
    task = SimpleNamespace(id="task-1", project_id="project-1")
    attachment = SimpleNamespace(
        id="attachment-1",
        filename="mockup.png",
        content_type="image/png",
        storage_path=str(image_path),
        alt_text=None,
    )

    async def fake_invoke_vision(
        *args,
        **kwargs,
    ) -> LLMInvocationResult:  # type: ignore[no-untyped-def]
        return LLMInvocationResult(
            ok=True,
            text="Макет экрана входа с полями email и пароль.",
            provider_config_id="provider-1",
            provider_kind="openai",
            model="gpt-4o",
            latency_ms=10,
            prompt_tokens=10,
            completion_tokens=10,
            total_tokens=20,
            estimated_cost_usd=None,
        )

    monkeypatch.setattr(
        "app.services.llm_runtime_service.LLMRuntimeService.invoke_vision",
        fake_invoke_vision,
    )

    payloads = await AttachmentContentService.build_attachment_payloads(
        db,  # type: ignore[arg-type]
        task,  # type: ignore[arg-type]
        [attachment],  # type: ignore[list-item]
        actor_user_id="user-1",
    )

    assert db.flushed is True
    assert attachment.alt_text == "Макет экрана входа с полями email и пароль."
    assert payloads[0]["alt_text"] == "Макет экрана входа с полями email и пароль."


@pytest.mark.asyncio
async def test_run_rag_pipeline_includes_image_alt_text_source() -> None:
    result = await run_rag_pipeline(
        task_id="task-1",
        title="Авторизация",
        content="Нужно реализовать вход пользователя.",
        tags=["auth"],
        attachments=[
            {
                "id": "attachment-1",
                "filename": "mockup.png",
                "content_type": "image/png",
                "basename": "stored.png",
                "alt_text": "Макет формы входа с кнопкой продолжить.",
                "is_image": True,
            }
        ],
        validation_result={"verdict": "approved", "issues": [], "questions": []},
    )

    image_chunks = [
        chunk for chunk in result["chunks"] if chunk["source_type"] == "attachment_image_alt_text"
    ]
    assert image_chunks
    assert image_chunks[0]["filename"] == "mockup.png"
    assert "Макет формы входа" in image_chunks[0]["content"]


@pytest.mark.asyncio
async def test_search_related_tasks_returns_empty_list_without_semantic_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_search_related_tasks(**kwargs):  # type: ignore[no-untyped-def]
        return []

    monkeypatch.setattr(
        "app.services.qdrant_service.QdrantService.search_related_tasks",
        fake_search_related_tasks,
    )

    result = await RagService.search_related_tasks(
        SimpleNamespace(),
        project_id="project-1",
        query_text="нет совпадений",
    )

    assert result == []
