from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response, status
from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services.audit_service import AuditService

settings = get_settings()


class AuthService:
    @staticmethod
    async def register(email: str, password: str, full_name: str, db: AsyncSession) -> User:
        stmt: Select[tuple[User]] = select(User).where(User.email == email)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Пользователь с таким email уже зарегистрирован",
            )

        total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
        initial_role = UserRole.ADMIN if total_users == 0 else UserRole.DEVELOPER
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=initial_role,
        )
        db.add(user)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=user.id,
            event_type="auth.registered",
            entity_type="user",
            entity_id=user.id,
            metadata={"role": user.role.value},
        )
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def login(
        email: str,
        password: str,
        db: AsyncSession,
        request: Request,
        response: Response,
    ) -> dict[str, str | int]:
        stmt: Select[tuple[User]] = select(User).where(User.email == email)
        user = (await db.execute(stmt)).scalar_one_or_none()

        if user is None or not user.is_active or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверные учётные данные",
            )

        access_token = create_access_token(user.id, user.role.value)
        raw_rt, hashed_rt = generate_refresh_token()

        refresh_token = RefreshToken(
            user_id=user.id,
            token_hash=hashed_rt,
            family_id=str(uuid.uuid4()),
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=request.headers.get("User-Agent"),
            ip_address=str(request.client.host) if request.client else None,
        )
        db.add(refresh_token)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=user.id,
            event_type="auth.login.success",
            entity_type="session",
            entity_id=refresh_token.id,
            metadata={"user_agent": refresh_token.user_agent},
        )
        await db.commit()

        AuthService._set_refresh_cookie(response, raw_rt)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    @staticmethod
    async def refresh(
        raw_rt: str,
        db: AsyncSession,
        request: Request,
        response: Response,
    ) -> dict[str, str | int]:
        token_hash = hash_refresh_token(raw_rt)
        stmt: Select[tuple[RefreshToken]] = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        token = (await db.execute(stmt)).scalar_one_or_none()

        if token is None:
            response.delete_cookie("refresh_token", domain=settings.COOKIE_DOMAIN)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Недействительный токен обновления",
            )

        now = datetime.now(timezone.utc)
        if token.revoked:
            await db.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == token.family_id)
                .values(revoked=True, revoked_at=now)
            )
            await db.commit()
            response.delete_cookie("refresh_token", domain=settings.COOKIE_DOMAIN)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Обнаружено повторное использование токена. Все сессии отозваны.",
            )

        if token.expires_at < now:
            token.revoked = True
            token.revoked_at = now
            await db.commit()
            response.delete_cookie("refresh_token", domain=settings.COOKIE_DOMAIN)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Срок действия токена обновления истёк",
            )

        token.revoked = True
        token.revoked_at = now

        user = await db.get(User, token.user_id)
        if user is None or not user.is_active:
            await db.commit()
            response.delete_cookie("refresh_token", domain=settings.COOKIE_DOMAIN)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Пользователь не найден или отключён",
            )

        access_token = create_access_token(user.id, user.role.value)
        new_raw_rt, new_hashed_rt = generate_refresh_token()
        new_token = RefreshToken(
            user_id=user.id,
            token_hash=new_hashed_rt,
            family_id=token.family_id,
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=request.headers.get("User-Agent"),
            ip_address=str(request.client.host) if request.client else None,
        )
        db.add(new_token)
        await db.flush()
        AuditService.record(
            db,
            actor_user_id=user.id,
            event_type="auth.refresh.success",
            entity_type="session",
            entity_id=new_token.id,
            metadata={"family_id": new_token.family_id},
        )
        await db.commit()

        AuthService._set_refresh_cookie(response, new_raw_rt)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        }

    @staticmethod
    async def logout(raw_rt: str | None, db: AsyncSession, response: Response) -> None:
        if raw_rt is None:
            response.delete_cookie("refresh_token", domain=settings.COOKIE_DOMAIN)
            return

        token_hash = hash_refresh_token(raw_rt)
        stmt: Select[tuple[RefreshToken]] = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        token = (await db.execute(stmt)).scalar_one_or_none()

        if token is not None and not token.revoked:
            token.revoked = True
            token.revoked_at = datetime.now(timezone.utc)
            AuditService.record(
                db,
                actor_user_id=token.user_id,
                event_type="auth.logout",
                entity_type="session",
                entity_id=token.id,
            )
            await db.commit()

        response.delete_cookie("refresh_token", domain=settings.COOKIE_DOMAIN)

    @staticmethod
    async def list_sessions(user_id: str, db: AsyncSession) -> list[RefreshToken]:
        stmt: Select[tuple[RefreshToken]] = (
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked.is_(False),
                RefreshToken.expires_at > datetime.now(timezone.utc),
            )
            .order_by(RefreshToken.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def revoke_session(session_id: str, user_id: str, db: AsyncSession) -> None:
        token = await db.get(RefreshToken, session_id)
        if token is None or token.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Сессия не найдена",
            )

        if not token.revoked:
            token.revoked = True
            token.revoked_at = datetime.now(timezone.utc)
            AuditService.record(
                db,
                actor_user_id=user_id,
                event_type="auth.session.revoked",
                entity_type="session",
                entity_id=token.id,
            )
            await db.commit()

    @staticmethod
    def _set_refresh_cookie(response: Response, raw_token: str) -> None:
        response.set_cookie(
            key="refresh_token",
            value=raw_token,
            max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
            httponly=True,
            secure=settings.COOKIE_SECURE,
            samesite=settings.COOKIE_SAMESITE,
            domain=settings.COOKIE_DOMAIN,
            path="/",
        )
