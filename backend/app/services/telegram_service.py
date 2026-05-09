from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from html import escape

from fastapi import HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.notification import TelegramConnection, TelegramLinkToken
from app.models.user import User
from app.schemas.notification import TelegramLinkTokenRead


class TelegramService:
    token_ttl_minutes = 15

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    async def create_link_token(user: User, db: AsyncSession) -> TelegramLinkTokenRead:
        now = datetime.now(UTC)
        await db.execute(
            delete(TelegramLinkToken)
            .where(TelegramLinkToken.user_id == user.id)
            .where(TelegramLinkToken.consumed_at.is_(None))
        )
        token = "-".join(secrets.token_hex(2).upper() for _ in range(3))
        expires_at = now + timedelta(minutes=TelegramService.token_ttl_minutes)
        db.add(
            TelegramLinkToken(
                user_id=user.id,
                token_hash=TelegramService._hash_token(token),
                expires_at=expires_at,
            )
        )
        await db.commit()

        settings = get_settings()
        deep_link = (
            f"https://t.me/{settings.TELEGRAM_BOT_USERNAME}?start={token}"
            if settings.TELEGRAM_BOT_USERNAME
            else None
        )
        return TelegramLinkTokenRead(token=token, expires_at=expires_at, deep_link=deep_link)

    @staticmethod
    async def unlink(user: User, db: AsyncSession) -> None:
        await db.execute(delete(TelegramConnection).where(TelegramConnection.user_id == user.id))
        await db.commit()

    @staticmethod
    async def consume_link_token(
        *,
        token: str,
        chat_id: str,
        telegram_user_id: str | None,
        telegram_username: str | None,
        db: AsyncSession,
    ) -> User | None:
        now = datetime.now(UTC)
        row = (
            await db.execute(
                select(TelegramLinkToken)
                .where(TelegramLinkToken.token_hash == TelegramService._hash_token(token.strip()))
                .where(TelegramLinkToken.consumed_at.is_(None))
                .where(TelegramLinkToken.expires_at > now)
            )
        ).scalar_one_or_none()
        if row is None:
            return None

        existing_connections = list(
            (
                await db.execute(
                    select(TelegramConnection).where(
                        or_(
                            TelegramConnection.user_id == row.user_id,
                            TelegramConnection.telegram_chat_id == chat_id,
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        existing = next(
            (
                connection
                for connection in existing_connections
                if connection.user_id == row.user_id
            ),
            None,
        )
        deleted_other_connection = False
        for connection in existing_connections:
            if connection.user_id != row.user_id:
                await db.delete(connection)
                deleted_other_connection = True
        if deleted_other_connection:
            await db.flush()

        if existing is None:
            db.add(
                TelegramConnection(
                    user_id=row.user_id,
                    telegram_chat_id=chat_id,
                    telegram_user_id=telegram_user_id,
                    telegram_username=telegram_username,
                    is_active=True,
                )
            )
        else:
            existing.telegram_chat_id = chat_id
            existing.telegram_user_id = telegram_user_id
            existing.telegram_username = telegram_username
            existing.is_active = True

        row.consumed_at = now
        await db.commit()
        return await db.get(User, row.user_id)

    @staticmethod
    async def send_message(chat_id: str, text: str) -> tuple[bool, str | None]:
        settings = get_settings()
        if not settings.TELEGRAM_BOT_TOKEN:
            return False, "Telegram bot token is not configured"

        try:
            from aiogram import Bot
            from aiogram.client.default import DefaultBotProperties
            from aiogram.enums import ParseMode
        except ImportError:
            return False, "aiogram is not installed"

        bot: Bot | None = None
        try:
            bot = Bot(
                token=settings.TELEGRAM_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            await bot.send_message(chat_id=chat_id, text=text, disable_notification=False)
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        finally:
            if bot is not None:
                await bot.session.close()
        return True, None

    @staticmethod
    def format_notification_text(title: str, body: str) -> str:
        escaped_title = escape(title)
        escaped_body = escape(body)
        if escaped_body:
            return f"<b>{escaped_title}</b>\n{escaped_body}"
        return f"<b>{escaped_title}</b>"

    @staticmethod
    def verify_webhook_secret(secret: str | None) -> None:
        settings = get_settings()
        if not settings.TELEGRAM_WEBHOOK_SECRET or secret != settings.TELEGRAM_WEBHOOK_SECRET:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
