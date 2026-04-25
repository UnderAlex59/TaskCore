from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.attachment_vision_graph import run_attachment_vision_graph
from app.core.config import get_settings
from app.models.task import Task, TaskAttachment

_TEXT_CONTENT_TYPES = {
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/x-yaml",
    "application/yaml",
}
_ALT_TEXT_PLACEHOLDER_PREFIXES = ("Uploaded file:", "Загруженный файл:")


class AttachmentContentService:
    @staticmethod
    def is_image(content_type: str | None) -> bool:
        normalized = (content_type or "").split(";", maxsplit=1)[0].strip().casefold()
        return normalized.startswith("image/")

    @staticmethod
    def is_text(content_type: str | None) -> bool:
        normalized = (content_type or "").split(";", maxsplit=1)[0].strip().casefold()
        return normalized.startswith("text/") or normalized in _TEXT_CONTENT_TYPES

    @staticmethod
    def _read_limited_bytes(path: Path, limit: int) -> bytes:
        with path.open("rb") as source:
            return source.read(limit + 1)[:limit]

    @staticmethod
    def _read_limited_bytes_with_overflow(path: Path, limit: int) -> tuple[bytes, bool]:
        with path.open("rb") as source:
            raw = source.read(limit + 1)
        return raw[:limit], len(raw) > limit

    @staticmethod
    def _normalized_content_type(content_type: str | None) -> str:
        return (content_type or "application/octet-stream").split(";", maxsplit=1)[0].strip()

    @staticmethod
    def _meaningful_alt_text(alt_text: str | None) -> str | None:
        normalized = (alt_text or "").strip()
        if not normalized:
            return None
        if any(normalized.startswith(prefix) for prefix in _ALT_TEXT_PLACEHOLDER_PREFIXES):
            return None
        return normalized

    @staticmethod
    def extract_text(path: Path, content_type: str | None) -> str | None:
        if not AttachmentContentService.is_text(content_type):
            return None
        settings = get_settings()
        try:
            raw = AttachmentContentService._read_limited_bytes(
                path,
                settings.RAG_ATTACHMENT_MAX_TEXT_CHARS * 4,
            )
        except OSError:
            return None
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                text = raw.decode(encoding).strip()[: settings.RAG_ATTACHMENT_MAX_TEXT_CHARS]
            except UnicodeDecodeError:
                continue
            return text or None
        return None

    @staticmethod
    async def ensure_image_alt_text(
        db: AsyncSession,
        task: Task,
        attachment: TaskAttachment,
        *,
        actor_user_id: str | None,
    ) -> str | None:
        if not AttachmentContentService.is_image(attachment.content_type):
            return attachment.alt_text

        existing_alt_text = AttachmentContentService._meaningful_alt_text(attachment.alt_text)
        if existing_alt_text:
            return existing_alt_text

        settings = get_settings()
        if not settings.RAG_VISION_ENABLED:
            return None

        path = Path(attachment.storage_path)
        try:
            image_bytes, overflow = AttachmentContentService._read_limited_bytes_with_overflow(
                path,
                settings.RAG_VISION_MAX_IMAGE_BYTES,
            )
        except OSError:
            return None
        if overflow:
            return None
        if not image_bytes:
            return None

        try:
            result = await run_attachment_vision_graph(
                db=db,
                actor_user_id=actor_user_id,
                task_id=task.id,
                project_id=task.project_id,
                image_bytes=image_bytes,
                content_type=AttachmentContentService._normalized_content_type(
                    attachment.content_type
                ),
            )
        except Exception:
            return None
        alt_text = (result.get("alt_text") or "").strip()
        if not alt_text:
            return None

        attachment.alt_text = alt_text
        await db.flush()
        return attachment.alt_text

    @staticmethod
    async def build_attachment_payloads(
        db: AsyncSession,
        task: Task,
        attachments: list[TaskAttachment],
        *,
        actor_user_id: str | None,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for attachment in attachments:
            path = Path(attachment.storage_path)
            extracted_text = AttachmentContentService.extract_text(
                path,
                attachment.content_type,
            )
            alt_text = await AttachmentContentService.ensure_image_alt_text(
                db,
                task,
                attachment,
                actor_user_id=actor_user_id,
            )
            payloads.append(
                {
                    "id": attachment.id,
                    "filename": attachment.filename,
                    "content_type": attachment.content_type,
                    "basename": path.name,
                    "extracted_text": extracted_text,
                    "alt_text": alt_text,
                    "is_image": AttachmentContentService.is_image(attachment.content_type),
                    "is_text": AttachmentContentService.is_text(attachment.content_type),
                }
            )
        return payloads
