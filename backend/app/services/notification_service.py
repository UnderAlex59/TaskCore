from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message
from app.models.notification import (
    ChatReadState,
    Notification,
    NotificationDelivery,
    NotificationDeliveryChannel,
    NotificationDeliveryStatus,
    NotificationPriority,
    NotificationType,
    TelegramConnection,
)
from app.models.task import Task, TaskStatus
from app.models.user import User
from app.schemas.notification import (
    ChatUnreadRead,
    NotificationPageRead,
    NotificationRead,
    NotificationSettingsRead,
    NotificationSettingsUpdate,
)
from app.services.notification_realtime import notification_connection_manager
from app.services.task_service import TaskService
from app.services.telegram_service import TelegramService

MENTION_PATTERN = re.compile(
    r"(?<![\w@.])@([\w.\-+]+@[\w.\-]+\.[\w.\-]+|[\w.\-]{2,100})",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class TaskNotificationSnapshot:
    id: str
    project_id: str
    title: str
    status: TaskStatus
    analyst_id: str
    reviewer_analyst_id: str | None
    developer_id: str | None
    tester_id: str | None
    updated_at: datetime | None


def serialize_notification(notification: Notification) -> NotificationRead:
    return NotificationRead(
        id=notification.id,
        user_id=notification.user_id,
        type=notification.type.value,
        priority=notification.priority.value,
        title=notification.title,
        body=notification.body,
        project_id=notification.project_id,
        task_id=notification.task_id,
        message_id=notification.message_id,
        metadata=notification.metadata_,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


class NotificationService:
    @staticmethod
    async def list_notifications(
        current_user: User,
        db: AsyncSession,
        *,
        unread_only: bool = False,
        read_state: str = "all",
        priority: str | None = None,
        type_: str | None = None,
        search: str | None = None,
        limit: int = 20,
    ) -> NotificationPageRead:
        stmt: Select[tuple[Notification]] = (
            select(Notification)
            .where(Notification.user_id == current_user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        effective_read_state = "unread" if unread_only else read_state
        if effective_read_state == "unread":
            stmt = stmt.where(Notification.read_at.is_(None))
        elif effective_read_state == "read":
            stmt = stmt.where(Notification.read_at.is_not(None))
        if priority:
            stmt = stmt.where(Notification.priority == NotificationPriority(priority))
        if type_:
            stmt = stmt.where(Notification.type == NotificationType(type_))
        normalized_search = search.strip() if search else ""
        if normalized_search:
            pattern = f"%{normalized_search}%"
            stmt = stmt.where(
                or_(
                    Notification.title.ilike(pattern),
                    Notification.body.ilike(pattern),
                )
            )

        items = list((await db.execute(stmt)).scalars().all())
        unread_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(Notification)
                    .where(Notification.user_id == current_user.id)
                    .where(Notification.read_at.is_(None))
                )
            ).scalar_one()
        )
        return NotificationPageRead(
            items=[serialize_notification(item) for item in items],
            unread_count=unread_count,
        )

    @staticmethod
    async def mark_read(
        notification_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> NotificationRead:
        notification = await db.get(Notification, notification_id)
        if notification is None or notification.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Уведомление не найдено",
            )
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await db.commit()
            await db.refresh(notification)
        return serialize_notification(notification)

    @staticmethod
    async def mark_all_read(current_user: User, db: AsyncSession) -> None:
        rows = list(
            (
                await db.execute(
                    select(Notification)
                    .where(Notification.user_id == current_user.id)
                    .where(Notification.read_at.is_(None))
                )
            )
            .scalars()
            .all()
        )
        now = datetime.now(UTC)
        for row in rows:
            row.read_at = now
        await db.commit()

    @staticmethod
    async def get_settings(current_user: User, db: AsyncSession) -> NotificationSettingsRead:
        connection = (
            await db.execute(
                select(TelegramConnection)
                .where(TelegramConnection.user_id == current_user.id)
                .where(TelegramConnection.is_active.is_(True))
            )
        ).scalar_one_or_none()
        settings = dict(current_user.notification_settings or {})
        return NotificationSettingsRead(
            telegram_important_enabled=bool(
                settings.get("telegram_important_enabled", True)
            ),
            telegram_normal_enabled=bool(settings.get("telegram_normal_enabled", True)),
            telegram_linked=connection is not None,
            telegram_username=connection.telegram_username if connection else None,
        )

    @staticmethod
    async def update_settings(
        current_user: User,
        payload: NotificationSettingsUpdate,
        db: AsyncSession,
    ) -> NotificationSettingsRead:
        settings = dict(current_user.notification_settings or {})
        updates = payload.model_dump(exclude_unset=True)
        if "telegram_important_enabled" in updates:
            settings["telegram_important_enabled"] = bool(
                updates["telegram_important_enabled"]
            )
        if "telegram_normal_enabled" in updates:
            settings["telegram_normal_enabled"] = bool(
                updates["telegram_normal_enabled"]
            )
        current_user.notification_settings = settings
        await db.commit()
        await db.refresh(current_user)
        return await NotificationService.get_settings(current_user, db)

    @staticmethod
    async def create_notification(
        db: AsyncSession,
        *,
        user_id: str,
        type_: NotificationType,
        priority: NotificationPriority,
        title: str,
        body: str,
        project_id: str | None = None,
        task_id: str | None = None,
        message_id: str | None = None,
        metadata: dict | None = None,
        dedupe_key: str | None = None,
    ) -> Notification | None:
        if dedupe_key:
            existing = (
                await db.execute(
                    select(Notification)
                    .where(Notification.user_id == user_id)
                    .where(Notification.dedupe_key == dedupe_key)
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        notification = Notification(
            user_id=user_id,
            type=type_,
            priority=priority,
            title=title,
            body=body,
            project_id=project_id,
            task_id=task_id,
            message_id=message_id,
            metadata_=metadata,
            dedupe_key=dedupe_key,
        )
        db.add(notification)
        await db.flush()
        db.add(
            NotificationDelivery(
                notification_id=notification.id,
                channel=NotificationDeliveryChannel.IN_APP,
                status=NotificationDeliveryStatus.SENT,
                sent_at=datetime.now(UTC),
            )
        )
        await NotificationService._deliver_telegram_if_needed(notification, db)
        await notification_connection_manager.broadcast_notifications(
            user_id,
            [serialize_notification(notification)],
        )
        return notification

    @staticmethod
    async def _deliver_telegram_if_needed(notification: Notification, db: AsyncSession) -> None:
        user = await db.get(User, notification.user_id)
        if user is None:
            return
        settings = dict(user.notification_settings or {})
        enabled_key = (
            "telegram_important_enabled"
            if notification.priority == NotificationPriority.IMPORTANT
            else "telegram_normal_enabled"
        )
        if not bool(settings.get(enabled_key, True)):
            db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel=NotificationDeliveryChannel.TELEGRAM,
                    status=NotificationDeliveryStatus.SKIPPED,
                    error="Telegram notifications are disabled for this priority",
                )
            )
            return

        connection = (
            await db.execute(
                select(TelegramConnection)
                .where(TelegramConnection.user_id == notification.user_id)
                .where(TelegramConnection.is_active.is_(True))
            )
        ).scalar_one_or_none()
        if connection is None:
            db.add(
                NotificationDelivery(
                    notification_id=notification.id,
                    channel=NotificationDeliveryChannel.TELEGRAM,
                    status=NotificationDeliveryStatus.SKIPPED,
                    error="Telegram is not linked",
                )
            )
            return

        ok, error = await TelegramService.send_message(
            connection.telegram_chat_id,
            TelegramService.format_notification_text(notification.title, notification.body),
        )
        db.add(
            NotificationDelivery(
                notification_id=notification.id,
                channel=NotificationDeliveryChannel.TELEGRAM,
                status=NotificationDeliveryStatus.SENT if ok else NotificationDeliveryStatus.FAILED,
                error=error,
                sent_at=datetime.now(UTC) if ok else None,
            )
        )

    @staticmethod
    async def notify_mentions_for_message(
        task: Task,
        message: Message,
        author: User,
        db: AsyncSession,
    ) -> None:
        mention_keys = {
            match.group(1).lower() for match in MENTION_PATTERN.finditer(message.content)
        }
        if not mention_keys:
            return

        stmt = select(User).where(
            or_(
                func.lower(User.email).in_(mention_keys),
                func.lower(User.nickname).in_(mention_keys),
            )
        )
        users = list((await db.execute(stmt)).scalars().all())
        for user in users:
            if user.id == author.id or not TaskService.can_access_chat(task, user):
                continue
            await NotificationService.create_notification(
                db,
                user_id=user.id,
                type_=NotificationType.CHAT_MENTION,
                priority=NotificationPriority.IMPORTANT,
                title="Вас упомянули в чате",
                body=f"{author.nickname or author.full_name}: {message.content[:240]}",
                project_id=task.project_id,
                task_id=task.id,
                message_id=message.id,
                dedupe_key=f"mention:{message.id}:{user.id}",
            )

    @staticmethod
    async def notify_chat_unread_for_message(
        task: Task,
        message: Message,
        db: AsyncSession,
    ) -> None:
        recipients = await NotificationService._task_chat_recipient_ids(task, db)
        if message.author_id:
            recipients.discard(message.author_id)
        for user_id in recipients:
            unread_count = await NotificationService.get_task_unread_count(task.id, user_id, db)
            await notification_connection_manager.broadcast_chat_unread(
                user_id,
                task.id,
                unread_count,
            )

    @staticmethod
    async def get_task_unread_state(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> ChatUnreadRead:
        task = await TaskService.get_task_with_chat_access(task_id, current_user, db)
        count = await NotificationService.get_task_unread_count(task.id, current_user.id, db)
        read_state = (
            await db.execute(
                select(ChatReadState)
                .where(ChatReadState.task_id == task.id)
                .where(ChatReadState.user_id == current_user.id)
            )
        ).scalar_one_or_none()
        return ChatUnreadRead(
            task_id=task.id,
            unread_count=count,
            last_read_at=read_state.last_read_at if read_state else None,
        )

    @staticmethod
    async def mark_task_chat_read(
        task_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> ChatUnreadRead:
        task = await TaskService.get_task_with_chat_access(task_id, current_user, db)
        now = datetime.now(UTC)
        stmt = (
            insert(ChatReadState)
            .values(task_id=task.id, user_id=current_user.id, last_read_at=now)
            .on_conflict_do_update(
                constraint="uq_chat_read_states_task_user",
                set_={"last_read_at": now, "updated_at": now},
            )
        )
        await db.execute(stmt)
        await db.commit()
        await notification_connection_manager.broadcast_chat_unread(current_user.id, task.id, 0)
        return ChatUnreadRead(task_id=task.id, unread_count=0, last_read_at=now)

    @staticmethod
    async def get_task_unread_count(task_id: str, user_id: str, db: AsyncSession) -> int:
        read_state = (
            await db.execute(
                select(ChatReadState)
                .where(ChatReadState.task_id == task_id)
                .where(ChatReadState.user_id == user_id)
            )
        ).scalar_one_or_none()
        stmt = select(func.count()).select_from(Message).where(Message.task_id == task_id)
        if read_state is not None:
            stmt = stmt.where(Message.created_at > read_state.last_read_at)
        stmt = stmt.where(or_(Message.author_id.is_(None), Message.author_id != user_id))
        return int((await db.execute(stmt)).scalar_one())

    @staticmethod
    async def request_analyst(
        task_id: str,
        message_id: str,
        current_user: User,
        db: AsyncSession,
    ) -> NotificationRead:
        task = await TaskService.get_task_with_chat_access(task_id, current_user, db)
        message = await db.get(Message, message_id)
        if message is None or message.task_id != task.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Сообщение не найдено",
            )
        source_ref = dict(message.source_ref or {})
        if (
            message.author_id is not None
            or message.agent_name != "QAAgent"
            or source_ref.get("answer_confidence") == "low"
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Аналитика можно позвать только по уверенному ответу QA.",
            )
        notification = await NotificationService.create_notification(
            db,
            user_id=task.analyst_id,
            type_=NotificationType.ANALYST_REQUESTED,
            priority=NotificationPriority.IMPORTANT,
            title="Требуется вмешательство аналитика",
            body=(
                f"{current_user.nickname or current_user.full_name} попросил проверить "
                f"ответ QA по задаче «{task.title}»."
            ),
            project_id=task.project_id,
            task_id=task.id,
            message_id=message.id,
            metadata={"requested_by": current_user.id},
            dedupe_key=f"analyst-request:{message.id}",
        )
        await db.commit()
        if notification is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Запрос уже отправлен")
        await db.refresh(notification)
        return serialize_notification(notification)

    @staticmethod
    async def notify_qa_needs_analyst(task: Task, message: Message, db: AsyncSession) -> None:
        await NotificationService.create_notification(
            db,
            user_id=task.analyst_id,
            type_=NotificationType.QA_NEEDS_ANALYST,
            priority=NotificationPriority.IMPORTANT,
            title="QA не нашел уверенный ответ",
            body=f"По задаче «{task.title}» нужен ответ аналитика.",
            project_id=task.project_id,
            task_id=task.id,
            message_id=message.id,
            metadata=message.source_ref,
            dedupe_key=f"qa-low-confidence:{message.id}",
        )

    @staticmethod
    async def notify_task_assigned(
        task: Task | TaskNotificationSnapshot,
        db: AsyncSession,
        *,
        assigned_user_ids: set[str],
    ) -> None:
        for user_id in assigned_user_ids:
            await NotificationService.create_notification(
                db,
                user_id=user_id,
                type_=NotificationType.TASK_ASSIGNED,
                priority=NotificationPriority.IMPORTANT,
                title="Вы назначены на задачу",
                body=f"Задача «{task.title}» теперь в вашей зоне ответственности.",
                project_id=task.project_id,
                task_id=task.id,
                dedupe_key=(
                    f"task-assigned:{task.id}:{user_id}:"
                    f"{task.updated_at.isoformat() if task.updated_at else ''}"
                ),
            )

    @staticmethod
    async def notify_task_status_changed(
        task: Task | TaskNotificationSnapshot,
        db: AsyncSession,
        *,
        actor_user_id: str | None = None,
    ) -> None:
        recipients = await NotificationService._task_chat_recipient_ids(task, db)
        if actor_user_id:
            recipients.discard(actor_user_id)
        for user_id in recipients:
            await NotificationService.create_notification(
                db,
                user_id=user_id,
                type_=NotificationType.TASK_STATUS_CHANGED,
                priority=NotificationPriority.NORMAL,
                title="Статус задачи изменился",
                body=f"Задача «{task.title}» перешла в статус {task.status.value}.",
                project_id=task.project_id,
                task_id=task.id,
                dedupe_key=(
                    f"task-status:{task.id}:{task.status.value}:"
                    f"{task.updated_at.isoformat() if task.updated_at else ''}:{user_id}"
                ),
            )

    @staticmethod
    async def _task_chat_recipient_ids(
        task: Task | TaskNotificationSnapshot,
        db: AsyncSession,
    ) -> set[str]:
        recipients = {task.analyst_id}
        if task.reviewer_analyst_id:
            recipients.add(task.reviewer_analyst_id)
        if task.status in TaskService.team_chat_statuses:
            if task.developer_id:
                recipients.add(task.developer_id)
            if task.tester_id:
                recipients.add(task.tester_id)
        return recipients
