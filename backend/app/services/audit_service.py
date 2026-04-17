from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent


class AuditService:
    @staticmethod
    def record(
        db: AsyncSession,
        *,
        actor_user_id: str | None,
        event_type: str,
        entity_type: str,
        entity_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        db.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                event_type=event_type,
                entity_type=entity_type,
                entity_id=entity_id,
                project_id=project_id,
                task_id=task_id,
                payload=metadata,
            )
        )
