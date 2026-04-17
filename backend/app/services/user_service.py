from __future__ import annotations

import re
import uuid
from pathlib import Path

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import HTTPException, status
from fastapi import UploadFile

from app.models.user import User
from app.schemas.auth import UserRead
from app.schemas.user import UserProfileUpdate, UserSummary, UserUpdate
from app.core.security import hash_password, verify_password
from app.services.audit_service import AuditService


class UserService:
    @staticmethod
    async def list_users(db: AsyncSession) -> list[UserSummary]:
        stmt: Select[tuple[User]] = select(User).order_by(User.created_at.asc())
        users = list((await db.execute(stmt)).scalars().all())
        return [UserSummary.model_validate(user) for user in users]

    @staticmethod
    async def update_user(
        user_id: str,
        payload: UserUpdate,
        actor: User,
        db: AsyncSession,
    ) -> UserSummary:
        user = await db.get(User, user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        if actor.id == user.id and payload.is_active is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя отключить собственный аккаунт",
            )

        for field_name, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, field_name, value)

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="user.updated",
            entity_type="user",
            entity_id=user.id,
            metadata=payload.model_dump(exclude_unset=True),
        )
        await db.commit()
        await db.refresh(user)
        return UserSummary.model_validate(user)

    @staticmethod
    async def update_current_user(
        user: User,
        payload: UserProfileUpdate,
        db: AsyncSession,
    ) -> UserRead:
        updates = payload.model_dump(exclude_unset=True)
        if "nickname" in updates:
            user.nickname = payload.nickname

        if payload.new_password is not None:
            if not verify_password(payload.current_password or "", user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Текущий пароль указан неверно",
                )
            user.password_hash = hash_password(payload.new_password)

        if payload.remove_avatar:
            user.avatar_url = None

        AuditService.record(
            db,
            actor_user_id=user.id,
            event_type="user.updated",
            entity_type="user",
            entity_id=user.id,
            metadata={
                "nickname_updated": "nickname" in updates,
                "password_updated": payload.new_password is not None,
                "avatar_removed": payload.remove_avatar,
            },
        )
        await db.commit()
        await db.refresh(user)
        return UserRead.model_validate(user)

    @staticmethod
    async def upload_avatar(
        user: User,
        file: UploadFile,
        db: AsyncSession,
        upload_dir: str,
    ) -> UserRead:
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Аватар должен быть изображением",
            )

        original_name = file.filename or "avatar"
        safe_stem = re.sub(r"[^\w.-]+", "_", Path(original_name).stem).strip("._") or "avatar"
        suffix = Path(original_name).suffix or ".png"
        target_dir = Path(upload_dir) / "avatars" / user.id
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_name = f"{uuid.uuid4().hex}_{safe_stem}{suffix}"
        target_path = target_dir / stored_name
        content = await file.read()
        target_path.write_bytes(content)

        user.avatar_url = f"/api/uploads/avatars/{user.id}/{stored_name}"
        AuditService.record(
            db,
            actor_user_id=user.id,
            event_type="user.updated",
            entity_type="user",
            entity_id=user.id,
            metadata={"avatar_uploaded": True, "filename": original_name},
        )
        await db.commit()
        await db.refresh(user)
        return UserRead.model_validate(user)
