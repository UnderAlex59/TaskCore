from __future__ import annotations

import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import Select, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.notification import (
    ChatReadState,
    Notification,
    TelegramConnection,
    TelegramLinkToken,
)
from app.models.project import ProjectMember
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.schemas.auth import UserRead
from app.schemas.user import UserProfileUpdate, UserSummary, UserUpdate
from app.services.audit_service import AuditService


class UserService:
    @staticmethod
    async def list_users(db: AsyncSession) -> list[UserSummary]:
        stmt: Select[tuple[User]] = (
            select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.asc())
        )
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
        if user is None or user.deleted_at is not None:
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
    async def delete_current_user(user: User, db: AsyncSession, upload_dir: str) -> None:
        await UserService._delete_user(target=user, actor=user, db=db, upload_dir=upload_dir)

    @staticmethod
    async def delete_user(user_id: str, actor: User, db: AsyncSession, upload_dir: str) -> None:
        user = await db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

        await UserService._delete_user(target=user, actor=actor, db=db, upload_dir=upload_dir)

    @staticmethod
    async def _delete_user(target: User, actor: User, db: AsyncSession, upload_dir: str) -> None:
        await UserService._ensure_not_last_active_admin(target, db)

        deleted_at = datetime.now(UTC)
        original_email = target.email
        original_role = (
            target.role.value if isinstance(target.role, UserRole) else str(target.role)
        )

        await db.execute(delete(RefreshToken).where(RefreshToken.user_id == target.id))
        await db.execute(delete(Notification).where(Notification.user_id == target.id))
        await db.execute(delete(TelegramConnection).where(TelegramConnection.user_id == target.id))
        await db.execute(delete(TelegramLinkToken).where(TelegramLinkToken.user_id == target.id))
        await db.execute(delete(ChatReadState).where(ChatReadState.user_id == target.id))
        await db.execute(delete(ProjectMember).where(ProjectMember.user_id == target.id))
        UserService._remove_avatar_files(target.id, upload_dir)

        target.email = f"deleted-{target.id}@deleted.local"
        target.password_hash = hash_password(uuid.uuid4().hex + uuid.uuid4().hex)
        target.full_name = "Удалённый пользователь"
        target.nickname = None
        target.avatar_url = None
        target.is_active = False
        target.deleted_at = deleted_at

        AuditService.record(
            db,
            actor_user_id=actor.id,
            event_type="user.deleted",
            entity_type="user",
            entity_id=target.id,
            metadata={
                "self_deleted": actor.id == target.id,
                "email": original_email,
                "role": original_role,
            },
        )
        await db.commit()

    @staticmethod
    async def _ensure_not_last_active_admin(target: User, db: AsyncSession) -> None:
        if target.role != UserRole.ADMIN or not target.is_active or target.deleted_at is not None:
            return

        remaining_admins = (
            await db.execute(
                select(func.count())
                .select_from(User)
                .where(
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                    User.id != target.id,
                )
            )
        ).scalar_one()
        if remaining_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Нельзя удалить последнего активного администратора",
            )

    @staticmethod
    def _remove_avatar_files(user_id: str, upload_dir: str) -> None:
        upload_root = Path(upload_dir).resolve()
        avatar_dir = (upload_root / "avatars" / user_id).resolve()
        if avatar_dir == upload_root or not avatar_dir.is_relative_to(upload_root):
            return
        shutil.rmtree(avatar_dir, ignore_errors=True)

    @staticmethod
    async def update_current_user(
        user: User,
        payload: UserProfileUpdate,
        db: AsyncSession,
    ) -> UserRead:
        if user.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Пользователь не найден",
            )

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
