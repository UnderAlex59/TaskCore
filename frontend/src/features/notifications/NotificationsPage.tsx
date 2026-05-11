import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  notificationsApi,
  type NotificationListParams,
  type NotificationRead,
  type NotificationReadState,
} from "@/api/notificationsApi";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  formatDateTimeFull,
  getNotificationTypeLabel,
} from "@/shared/lib/locale";
import { notifyNotificationsChanged } from "@/shared/lib/notificationEvents";

type PriorityFilter = "all" | "important" | "normal";
type TypeFilter =
  | "all"
  | "analyst_requested"
  | "chat_mention"
  | "qa_needs_analyst"
  | "task_assigned"
  | "task_status_changed";

const READ_FILTERS: Array<{ label: string; value: NotificationReadState }> = [
  { label: "Все", value: "all" },
  { label: "Непрочитанные", value: "unread" },
  { label: "Прочитанные", value: "read" },
];

const PRIORITY_FILTERS: Array<{ label: string; value: PriorityFilter }> = [
  { label: "Все", value: "all" },
  { label: "Важные", value: "important" },
  { label: "Обычные", value: "normal" },
];

const TYPE_FILTERS: Array<{ label: string; value: TypeFilter }> = [
  { label: "Все типы", value: "all" },
  { label: "QA требует аналитика", value: "qa_needs_analyst" },
  { label: "Запрос аналитика", value: "analyst_requested" },
  { label: "Назначение на задачу", value: "task_assigned" },
  { label: "Изменение статуса задачи", value: "task_status_changed" },
  { label: "Упоминание в чате", value: "chat_mention" },
];

function getNotificationHref(item: NotificationRead) {
  return item.project_id && item.task_id
    ? `/projects/${item.project_id}/tasks/${item.task_id}`
    : "/projects";
}

function getPriorityLabel(priority: NotificationRead["priority"]) {
  return priority === "important" ? "Важное" : "Обычное";
}

function getReadLabel(item: NotificationRead) {
  return item.read_at ? "Прочитано" : "Новое";
}

export default function NotificationsPage() {
  const [items, setItems] = useState<NotificationRead[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [readState, setReadState] = useState<NotificationReadState>("all");
  const [priority, setPriority] = useState<PriorityFilter>("all");
  const [type, setType] = useState<TypeFilter>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search);

  const visibleUnreadItems = useMemo(
    () => items.filter((item) => !item.read_at),
    [items],
  );

  async function loadNotifications() {
    try {
      setLoading(true);
      setError(null);
      const trimmedSearch = deferredSearch.trim();
      const params: NotificationListParams = {
        limit: 100,
        read_state: readState,
      };
      if (priority !== "all") {
        params.priority = priority;
      }
      if (type !== "all") {
        params.type = type;
      }
      if (trimmedSearch) {
        params.search = trimmedSearch;
      }
      const payload = await notificationsApi.list(params);
      setItems(payload.items);
      setUnreadCount(payload.unread_count);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить уведомления."),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function loadActiveNotifications() {
      try {
        setLoading(true);
        setError(null);
        const trimmedSearch = deferredSearch.trim();
        const params: NotificationListParams = {
          limit: 100,
          read_state: readState,
        };
        if (priority !== "all") {
          params.priority = priority;
        }
        if (type !== "all") {
          params.type = type;
        }
        if (trimmedSearch) {
          params.search = trimmedSearch;
        }
        const payload = await notificationsApi.list(params);
        if (!active) {
          return;
        }
        setItems(payload.items);
        setUnreadCount(payload.unread_count);
      } catch (caught) {
        if (active) {
          setError(
            getApiErrorMessage(caught, "Не удалось загрузить уведомления."),
          );
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }
    void loadActiveNotifications();
    return () => {
      active = false;
    };
  }, [deferredSearch, priority, readState, type]);

  async function handleMarkRead(item: NotificationRead) {
    if (item.read_at) {
      return;
    }
    try {
      setActionBusy(item.id);
      setError(null);
      const updated = await notificationsApi.markRead(item.id);
      setItems((current) =>
        current.map((currentItem) =>
          currentItem.id === updated.id ? updated : currentItem,
        ),
      );
      setUnreadCount((count) => Math.max(0, count - 1));
      notifyNotificationsChanged();
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось отметить уведомление."),
      );
    } finally {
      setActionBusy(null);
    }
  }

  async function handleMarkVisibleRead() {
    if (visibleUnreadItems.length === 0) {
      return;
    }
    try {
      setActionBusy("visible");
      setError(null);
      await Promise.all(
        visibleUnreadItems.map((item) => notificationsApi.markRead(item.id)),
      );
      notifyNotificationsChanged();
      await loadNotifications();
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось отметить найденные уведомления."),
      );
    } finally {
      setActionBusy(null);
    }
  }

  async function handleMarkAllRead() {
    try {
      setActionBusy("all");
      setError(null);
      await notificationsApi.markAllRead();
      notifyNotificationsChanged();
      await loadNotifications();
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось отметить все уведомления."),
      );
    } finally {
      setActionBusy(null);
    }
  }

  return (
    <section className="space-y-5">
      <header className="page-panel px-5 py-5 sm:px-7 sm:py-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div className="min-w-0">
            <p className="section-eyebrow">Уведомления</p>
            <h2 className="mt-3 text-3xl font-semibold text-[#172b4d]">
              Реестр уведомлений
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-[#44546f]">
              Полная история системных уведомлений по задачам, чату и
              назначенным действиям.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="metric-tile">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                В реестре
              </p>
              <p className="mt-2 text-2xl font-semibold text-[#172b4d]">
                {items.length}
              </p>
            </div>
            <div className="metric-tile">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                Непрочитано
              </p>
              <p className="mt-2 text-2xl font-semibold text-[#172b4d]">
                {unreadCount}
              </p>
            </div>
          </div>
        </div>
      </header>

      <section className="page-panel px-4 py-4 sm:px-5">
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_220px_260px]">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Статус
            </p>
            <div className="flex flex-wrap gap-2">
              {READ_FILTERS.map((item) => (
                <button
                  className={
                    item.value === readState
                      ? "ui-button-primary"
                      : "ui-button-secondary"
                  }
                  key={item.value}
                  onClick={() => setReadState(item.value)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Важность
            </span>
            <select
              className="ui-field"
              onChange={(event) => setPriority(event.target.value as PriorityFilter)}
              value={priority}
            >
              {PRIORITY_FILTERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Тип
            </span>
            <select
              className="ui-field"
              onChange={(event) => setType(event.target.value as TypeFilter)}
              value={type}
            >
              {TYPE_FILTERS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-4 flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
          <label className="block min-w-0 flex-1">
            <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Поиск
            </span>
            <input
              className="ui-field"
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Заголовок или текст уведомления"
              type="search"
              value={search}
            />
          </label>
          <div className="flex flex-col gap-2 sm:flex-row">
            <button
              className="ui-button-secondary"
              disabled={actionBusy !== null || visibleUnreadItems.length === 0}
              onClick={() => void handleMarkVisibleRead()}
              type="button"
            >
              Отметить найденные
            </button>
            <button
              className="ui-button-secondary"
              disabled={actionBusy !== null || unreadCount === 0}
              onClick={() => void handleMarkAllRead()}
              type="button"
            >
              Прочитать все
            </button>
          </div>
        </div>

        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-[12px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]"
          >
            {error}
          </p>
        ) : null}
      </section>

      {loading ? (
        <LoadingSpinner label="Загрузка уведомлений" />
      ) : (
        <section className="page-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-[rgba(9,30,66,0.1)] text-left text-sm">
              <thead className="bg-[#fafbfc] text-xs uppercase tracking-[0.12em] text-[#5e6c84]">
                <tr>
                  <th className="px-4 py-3 font-semibold">Уведомление</th>
                  <th className="px-4 py-3 font-semibold">Тип</th>
                  <th className="px-4 py-3 font-semibold">Важность</th>
                  <th className="px-4 py-3 font-semibold">Статус</th>
                  <th className="px-4 py-3 font-semibold">Время</th>
                  <th className="px-4 py-3 font-semibold">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[rgba(9,30,66,0.08)]">
                {items.map((item) => (
                  <tr
                    className={item.read_at ? "bg-white" : "bg-[#f8fbff]"}
                    key={item.id}
                  >
                    <td className="min-w-[20rem] px-4 py-4 align-top">
                      <p className="text-anywhere font-semibold text-[#172b4d]">
                        {item.title}
                      </p>
                      {item.body ? (
                        <p className="text-anywhere mt-1 max-w-2xl leading-6 text-[#44546f]">
                          {item.body}
                        </p>
                      ) : null}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 align-top text-[#44546f]">
                      {getNotificationTypeLabel(item.type)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 align-top">
                      <span
                        className={
                          item.priority === "important"
                            ? "status-pill border-[#f2b705]/30 bg-[#fff4e5] text-[#7f4c00]"
                            : "status-pill border-[rgba(9,30,66,0.12)] bg-[#f7f8fa] text-[#44546f]"
                        }
                      >
                        {getPriorityLabel(item.priority)}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 align-top">
                      <span
                        className={
                          item.read_at
                            ? "status-pill border-[rgba(9,30,66,0.12)] bg-white text-[#626f86]"
                            : "status-pill border-[#bfd4f6] bg-[#e9f2ff] text-[#0c66e4]"
                        }
                      >
                        {getReadLabel(item)}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-4 align-top text-[#626f86]">
                      {formatDateTimeFull(item.created_at)}
                    </td>
                    <td className="px-4 py-4 align-top">
                      <div className="flex flex-col gap-2">
                        <Link
                          className="ui-button-secondary px-3 py-2 text-xs"
                          onClick={() => void handleMarkRead(item)}
                          to={getNotificationHref(item)}
                        >
                          Открыть
                        </Link>
                        <button
                          className="ui-button-secondary px-3 py-2 text-xs"
                          disabled={Boolean(item.read_at) || actionBusy !== null}
                          onClick={() => void handleMarkRead(item)}
                          type="button"
                        >
                          Прочитано
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {items.length === 0 ? (
            <p className="px-5 py-8 text-sm leading-6 text-[#626f86]">
              По выбранным фильтрам уведомлений нет.
            </p>
          ) : null}
        </section>
      )}
    </section>
  );
}
