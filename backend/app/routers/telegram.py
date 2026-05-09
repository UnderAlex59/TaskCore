from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.dependencies import CurrentUser, DBSession
from app.schemas.notification import TelegramLinkTokenRead, TelegramWebhookResponse
from app.services.telegram_service import TelegramService

router = APIRouter(tags=["telegram"])


@router.post("/users/me/telegram-link-token", response_model=TelegramLinkTokenRead)
async def create_telegram_link_token(
    current_user: CurrentUser,
    db: DBSession,
) -> TelegramLinkTokenRead:
    return await TelegramService.create_link_token(current_user, db)


@router.delete("/users/me/telegram", status_code=204)
async def unlink_telegram(current_user: CurrentUser, db: DBSession) -> None:
    await TelegramService.unlink(current_user, db)


@router.post("/telegram/webhook", response_model=TelegramWebhookResponse)
async def telegram_webhook(
    request: Request,
    db: DBSession,
) -> TelegramWebhookResponse:
    TelegramService.verify_webhook_secret(
        request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    )
    payload = await request.json()
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        return TelegramWebhookResponse(ok=True, message="ignored")

    text = str(message.get("text") or "").strip()
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
    chat_id = str(chat.get("id") or "").strip()
    if not text or not chat_id:
        return TelegramWebhookResponse(ok=True, message="ignored")

    link_token = text.removeprefix("/start").strip()
    linked_user = await TelegramService.consume_link_token(
        token=link_token,
        chat_id=chat_id,
        telegram_user_id=str(from_user.get("id")) if from_user.get("id") else None,
        telegram_username=str(from_user.get("username")) if from_user.get("username") else None,
        db=db,
    )
    if linked_user is None:
        await TelegramService.send_message(
            chat_id,
            "Код не найден или устарел. Получите новую ссылку в профиле системы.",
        )
        return TelegramWebhookResponse(ok=True, message="invalid token")

    await TelegramService.send_message(
        chat_id,
        f"Telegram привязан к пользователю {linked_user.email}.",
    )
    return TelegramWebhookResponse(ok=True, message="linked")
