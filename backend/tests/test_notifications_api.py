from __future__ import annotations

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.notification import (
    NotificationDelivery,
    NotificationDeliveryChannel,
    NotificationDeliveryStatus,
    NotificationPriority,
    NotificationType,
    TelegramConnection,
)
from app.models.user import User
from app.services.notification_service import NotificationService
from app.services.telegram_service import TelegramService

pytestmark = pytest.mark.requires_db


async def register_user(
    client: AsyncClient,
    *,
    email: str,
    full_name: str,
    password: str = "StrongPass1",
) -> None:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201


async def login_user(
    client: AsyncClient,
    *,
    email: str,
    password: str = "StrongPass1",
) -> str:
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def get_user_by_email(email: str) -> User:
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        return user


async def test_notification_list_and_mark_read(client: AsyncClient) -> None:
    await register_user(client, email="notify@example.com", full_name="Nina Notify")
    token = await login_user(client, email="notify@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    user = await get_user_by_email("notify@example.com")

    async with AsyncSessionLocal() as db:
        await NotificationService.create_notification(
            db,
            user_id=user.id,
            type_=NotificationType.TASK_ASSIGNED,
            priority=NotificationPriority.IMPORTANT,
            title="Вы назначены на задачу",
            body="Проверьте новую задачу.",
        )
        await db.commit()

    list_response = await client.get("/notifications", headers=headers)
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["unread_count"] == 1
    notification = payload["items"][0]
    assert notification["title"] == "Вы назначены на задачу"
    assert notification["read_at"] is None

    read_response = await client.patch(
        f"/notifications/{notification['id']}/read",
        headers=headers,
    )
    assert read_response.status_code == 200
    assert read_response.json()["read_at"] is not None

    refreshed_response = await client.get("/notifications", headers=headers)
    assert refreshed_response.status_code == 200
    assert refreshed_response.json()["unread_count"] == 0


async def test_notification_list_filters_current_user_items(client: AsyncClient) -> None:
    await register_user(client, email="filter-owner@example.com", full_name="Filter Owner")
    await register_user(client, email="filter-other@example.com", full_name="Filter Other")
    token = await login_user(client, email="filter-owner@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    owner = await get_user_by_email("filter-owner@example.com")
    other = await get_user_by_email("filter-other@example.com")

    async with AsyncSessionLocal() as db:
        await NotificationService.create_notification(
            db,
            user_id=owner.id,
            type_=NotificationType.TASK_ASSIGNED,
            priority=NotificationPriority.IMPORTANT,
            title="Срочно проверить задачу",
            body="Проверьте новую задачу.",
        )
        read_notification = await NotificationService.create_notification(
            db,
            user_id=owner.id,
            type_=NotificationType.TASK_STATUS_CHANGED,
            priority=NotificationPriority.NORMAL,
            title="Статус изменился",
            body="Задача перешла в новый статус.",
        )
        await NotificationService.create_notification(
            db,
            user_id=owner.id,
            type_=NotificationType.CHAT_MENTION,
            priority=NotificationPriority.NORMAL,
            title="Вас упомянули в чате",
            body="Посмотрите обсуждение.",
        )
        await NotificationService.create_notification(
            db,
            user_id=other.id,
            type_=NotificationType.TASK_ASSIGNED,
            priority=NotificationPriority.IMPORTANT,
            title="Срочно проверить задачу",
            body="Чужое уведомление не должно попасть в выдачу.",
        )
        assert read_notification is not None
        read_notification.read_at = datetime.now(UTC)
        await db.commit()

    all_response = await client.get("/notifications", headers=headers)
    assert all_response.status_code == 200
    all_payload = all_response.json()
    assert all_payload["unread_count"] == 2
    assert len(all_payload["items"]) == 3

    unread_response = await client.get(
        "/notifications",
        headers=headers,
        params={"unread_only": True},
    )
    assert unread_response.status_code == 200
    assert len(unread_response.json()["items"]) == 2
    assert all(item["read_at"] is None for item in unread_response.json()["items"])

    read_response = await client.get(
        "/notifications",
        headers=headers,
        params={"read_state": "read"},
    )
    assert read_response.status_code == 200
    assert [item["title"] for item in read_response.json()["items"]] == [
        "Статус изменился"
    ]

    important_response = await client.get(
        "/notifications",
        headers=headers,
        params={"priority": "important"},
    )
    assert important_response.status_code == 200
    assert [item["title"] for item in important_response.json()["items"]] == [
        "Срочно проверить задачу"
    ]

    mention_response = await client.get(
        "/notifications",
        headers=headers,
        params={"type": "chat_mention"},
    )
    assert mention_response.status_code == 200
    assert [item["type"] for item in mention_response.json()["items"]] == [
        "chat_mention"
    ]

    search_response = await client.get(
        "/notifications",
        headers=headers,
        params={"search": "проверить"},
    )
    assert search_response.status_code == 200
    assert [item["title"] for item in search_response.json()["items"]] == [
        "Срочно проверить задачу"
    ]


async def test_telegram_link_token_can_be_consumed_once(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "TaskBot")
    get_settings.cache_clear()
    await register_user(client, email="telegram@example.com", full_name="Tanya Telegram")
    token = await login_user(client, email="telegram@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    token_response = await client.post("/users/me/telegram-link-token", headers=headers)
    assert token_response.status_code == 200
    link_token = token_response.json()["token"]
    assert token_response.json()["deep_link"] == f"https://t.me/TaskBot?start={link_token}"

    async with AsyncSessionLocal() as db:
        linked_user = await TelegramService.consume_link_token(
            token=link_token,
            chat_id="42",
            telegram_user_id="42",
            telegram_username="tanya",
            db=db,
        )
        assert linked_user is not None
        assert linked_user.email == "telegram@example.com"

    async with AsyncSessionLocal() as db:
        reused_user = await TelegramService.consume_link_token(
            token=link_token,
            chat_id="42",
            telegram_user_id="42",
            telegram_username="tanya",
            db=db,
        )
        assert reused_user is None

    settings_response = await client.get("/users/me/notification-settings", headers=headers)
    assert settings_response.status_code == 200
    assert settings_response.json()["telegram_linked"] is True
    assert settings_response.json()["telegram_username"] == "tanya"
    get_settings.cache_clear()


async def test_telegram_webhook_links_user_with_valid_secret(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    get_settings.cache_clear()
    await register_user(client, email="webhook-telegram@example.com", full_name="Webhook User")
    token = await login_user(client, email="webhook-telegram@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    token_response = await client.post("/users/me/telegram-link-token", headers=headers)
    link_token = token_response.json()["token"]

    sent_messages: list[tuple[str, str]] = []

    async def fake_send_message(chat_id: str, text: str) -> tuple[bool, str | None]:
        sent_messages.append((chat_id, text))
        return True, None

    monkeypatch.setattr(TelegramService, "send_message", fake_send_message)

    response = await client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={
            "message": {
                "text": f"/start {link_token}",
                "chat": {"id": 100500},
                "from": {"id": 42, "username": "webhook_telegram"},
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["message"] == "linked"
    assert sent_messages[0][0] == "100500"

    user = await get_user_by_email("webhook-telegram@example.com")
    async with AsyncSessionLocal() as db:
        connection = (
            await db.execute(
                select(TelegramConnection).where(TelegramConnection.user_id == user.id)
            )
        ).scalar_one()
        assert connection.telegram_chat_id == "100500"
        assert connection.telegram_user_id == "42"
        assert connection.telegram_username == "webhook_telegram"
    get_settings.cache_clear()


async def test_telegram_webhook_rejects_invalid_secret(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    get_settings.cache_clear()

    response = await client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={"message": {"text": "token", "chat": {"id": 42}}},
    )

    assert response.status_code == 404
    get_settings.cache_clear()


async def test_notifications_deliver_normal_and_important_to_telegram(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await register_user(
        client,
        email="deliver-telegram@example.com",
        full_name="Deliver Telegram",
    )
    user = await get_user_by_email("deliver-telegram@example.com")
    sent_messages: list[tuple[str, str]] = []

    async def fake_send_message(chat_id: str, text: str) -> tuple[bool, str | None]:
        sent_messages.append((chat_id, text))
        return True, None

    monkeypatch.setattr(TelegramService, "send_message", fake_send_message)

    async with AsyncSessionLocal() as db:
        db.add(
            TelegramConnection(
                user_id=user.id,
                telegram_chat_id="100500",
                telegram_user_id="42",
                telegram_username="deliver_telegram",
                is_active=True,
            )
        )
        await db.flush()
        important = await NotificationService.create_notification(
            db,
            user_id=user.id,
            type_=NotificationType.TASK_ASSIGNED,
            priority=NotificationPriority.IMPORTANT,
            title="Вы назначены на задачу",
            body="Проверьте задачу.",
        )
        normal = await NotificationService.create_notification(
            db,
            user_id=user.id,
            type_=NotificationType.TASK_STATUS_CHANGED,
            priority=NotificationPriority.NORMAL,
            title="Статус задачи изменился",
            body="Задача перешла в новый статус.",
        )
        await db.commit()

        deliveries = list(
            (
                await db.execute(
                    select(NotificationDelivery).where(
                        NotificationDelivery.channel == NotificationDeliveryChannel.TELEGRAM
                    )
                )
            )
            .scalars()
            .all()
        )

    assert important is not None
    assert normal is not None
    assert sent_messages == [
        ("100500", "<b>Вы назначены на задачу</b>\nПроверьте задачу."),
        ("100500", "<b>Статус задачи изменился</b>\nЗадача перешла в новый статус."),
    ]
    assert len(deliveries) == 2
    assert {delivery.status for delivery in deliveries} == {NotificationDeliveryStatus.SENT}


async def test_telegram_delivery_skipped_when_not_linked_or_disabled(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await register_user(client, email="skip-telegram@example.com", full_name="Skip Telegram")
    user = await get_user_by_email("skip-telegram@example.com")

    async def fail_if_called(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Telegram delivery should have been skipped")

    monkeypatch.setattr(TelegramService, "send_message", fail_if_called)

    async with AsyncSessionLocal() as db:
        skipped_without_link = await NotificationService.create_notification(
            db,
            user_id=user.id,
            type_=NotificationType.TASK_STATUS_CHANGED,
            priority=NotificationPriority.NORMAL,
            title="Статус задачи изменился",
            body="Нет привязки Telegram.",
        )
        db.add(
            TelegramConnection(
                user_id=user.id,
                telegram_chat_id="42",
                telegram_user_id="42",
                telegram_username="skip_telegram",
                is_active=True,
            )
        )
        user_in_db = await db.get(User, user.id)
        assert user_in_db is not None
        user_in_db.notification_settings = {
            "telegram_important_enabled": True,
            "telegram_normal_enabled": False,
        }
        await db.flush()
        skipped_disabled = await NotificationService.create_notification(
            db,
            user_id=user.id,
            type_=NotificationType.TASK_STATUS_CHANGED,
            priority=NotificationPriority.NORMAL,
            title="Статус задачи изменился",
            body="Обычные Telegram-уведомления отключены.",
        )
        await db.commit()

        deliveries = list(
            (
                await db.execute(
                    select(NotificationDelivery)
                    .where(NotificationDelivery.channel == NotificationDeliveryChannel.TELEGRAM)
                    .order_by(NotificationDelivery.created_at)
                )
            )
            .scalars()
            .all()
        )

    assert skipped_without_link is not None
    assert skipped_disabled is not None
    assert [delivery.status for delivery in deliveries] == [
        NotificationDeliveryStatus.SKIPPED,
        NotificationDeliveryStatus.SKIPPED,
    ]
