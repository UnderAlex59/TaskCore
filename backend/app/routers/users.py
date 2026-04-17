from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.core.config import get_settings
from app.core.dependencies import CurrentUser, DBSession, require_role
from app.models.user import User, UserRole
from app.schemas.auth import UserRead
from app.schemas.user import UserProfileUpdate, UserSummary, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])
settings = get_settings()


@router.get("", response_model=list[UserSummary])
async def list_users(
    _: CurrentUser,
    db: DBSession,
) -> list[UserSummary]:
    return await UserService.list_users(db)


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserProfileUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserRead:
    return await UserService.update_current_user(current_user, payload, db)


@router.post("/me/avatar", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def upload_my_avatar(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
) -> UserRead:
    return await UserService.upload_avatar(current_user, file, db, settings.UPLOAD_DIR)


@router.patch("/{user_id}", response_model=UserSummary)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: Annotated[User, Depends(require_role(UserRole.ADMIN))],
    db: DBSession,
) -> UserSummary:
    return await UserService.update_user(user_id, payload, current_user, db)
