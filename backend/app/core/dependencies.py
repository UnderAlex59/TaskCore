from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import decode_access_token
from app.models.project import ProjectMember
from app.models.user import User, UserRole

bearer = HTTPBearer(auto_error=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: DBSession,
) -> User:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется авторизация",
        )

    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload["sub"]
    except (JWTError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен",
        ) from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден или отключён",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

ROLE_LABELS: dict[UserRole, str] = {
    UserRole.ADMIN: "администратор",
    UserRole.ANALYST: "аналитик",
    UserRole.DEVELOPER: "разработчик",
    UserRole.TESTER: "тестировщик",
    UserRole.MANAGER: "менеджер",
}


def require_role(*roles: UserRole):
    async def _check(current_user: CurrentUser) -> User:
        if current_user.role not in roles:
            role_names = ", ".join(ROLE_LABELS.get(role, role.value.lower()) for role in roles)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Требуются роли: {role_names}",
            )
        return current_user

    return _check


async def require_project_member(
    project_id: str,
    current_user: CurrentUser,
    db: DBSession,
) -> User:
    if current_user.role == UserRole.ADMIN:
        return current_user

    stmt = select(ProjectMember).where(
        ProjectMember.project_id == project_id,
        ProjectMember.user_id == current_user.id,
    )
    membership = (await db.execute(stmt)).scalar_one_or_none()
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пользователь не состоит в проекте",
        )
    return current_user
