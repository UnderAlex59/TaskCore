import { startTransition, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { authApi } from "@/api/authApi";
import {
  notificationsApi,
  type NotificationRead,
  type NotificationRealtimeEvent,
} from "@/api/notificationsApi";
import { Avatar } from "@/shared/components/Avatar";
import { formatDateTime, getRoleLabel } from "@/shared/lib/locale";
import { getUserDisplayName } from "@/shared/lib/userProfile";
import { useAuthStore } from "@/store/authStore";

const navItems = [
  { href: "/projects", label: "Проекты", description: "Задачи, роли, правила" },
  { href: "/profile", label: "Профиль", description: "Учетная запись" },
  {
    href: "/admin/monitoring",
    label: "Администрирование",
    description: "Настройки системы",
  },
];

function mergeNotifications(
  current: NotificationRead[],
  incoming: NotificationRead[],
) {
  const merged = new Map(current.map((item) => [item.id, item]));
  for (const item of incoming) {
    merged.set(item.id, item);
  }
  return [...merged.values()]
    .sort(
      (left, right) =>
        new Date(right.created_at).getTime() -
        new Date(left.created_at).getTime(),
    )
    .slice(0, 20);
}

function NotificationCenter() {
  const accessToken = useAuthStore((state) => state.accessToken);
  const [items, setItems] = useState<NotificationRead[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!accessToken) {
      setItems([]);
      setUnreadCount(0);
      return;
    }

    let active = true;
    void notificationsApi.list({ limit: 10 }).then((payload) => {
      if (!active) {
        return;
      }
      setItems(payload.items);
      setUnreadCount(payload.unread_count);
    });

    return () => {
      active = false;
    };
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    let reconnectTimer: number | null = null;
    let socket: WebSocket | null = null;
    let closed = false;

    const connect = () => {
      if (closed) {
        return;
      }
      socket = notificationsApi.connect(accessToken);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as NotificationRealtimeEvent;
          if (
            payload.type === "notifications.created" &&
            Array.isArray(payload.notifications)
          ) {
            setItems((current) =>
              mergeNotifications(current, payload.notifications ?? []),
            );
            setUnreadCount(
              (count) => count + (payload.notifications?.length ?? 0),
            );
          }
        } catch {
          // Realtime payload can be ignored without breaking the session.
        }
      };
      socket.onclose = () => {
        if (!closed) {
          reconnectTimer = window.setTimeout(connect, 1500);
        }
      };
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [accessToken]);

  const unreadLabel = useMemo(
    () => (unreadCount > 99 ? "99+" : String(unreadCount)),
    [unreadCount],
  );

  async function handleMarkRead(notification: NotificationRead) {
    if (notification.read_at) {
      return;
    }
    const updated = await notificationsApi.markRead(notification.id);
    setItems((current) =>
      current.map((item) => (item.id === updated.id ? updated : item)),
    );
    setUnreadCount((count) => Math.max(0, count - 1));
  }

  async function handleMarkAllRead() {
    await notificationsApi.markAllRead();
    const now = new Date().toISOString();
    setItems((current) => current.map((item) => ({ ...item, read_at: now })));
    setUnreadCount(0);
  }

  return (
    <div className="relative">
      <button
        className="ui-button-secondary w-full justify-between"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <span>Уведомления</span>
        {unreadCount > 0 ? (
          <span className="ml-3 rounded-full bg-[#0c66e4] px-2 py-0.5 text-xs font-semibold text-white">
            {unreadLabel}
          </span>
        ) : (
          <span className="ml-3 text-xs font-medium text-[#626f86]">
            нет новых
          </span>
        )}
      </button>

      {open ? (
        <div className="absolute bottom-[calc(100%+0.5rem)] left-0 z-40 w-full min-w-0 overflow-hidden rounded-[14px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_18px_40px_rgba(9,30,66,0.16)]">
          <div className="flex items-center justify-between gap-3 border-b border-[rgba(9,30,66,0.08)] px-4 py-3">
            <p className="text-sm font-semibold text-[#172b4d]">
              Центр уведомлений
            </p>
            <button
              className="text-xs font-semibold text-[#0c66e4] disabled:text-[#7a869a]"
              disabled={unreadCount === 0}
              onClick={() => void handleMarkAllRead()}
              type="button"
            >
              Прочитано
            </button>
          </div>
          <div className="max-h-[22rem] overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-4 py-5 text-sm leading-6 text-[#626f86]">
                Новых уведомлений пока нет.
              </p>
            ) : (
              items.map((item) => {
                const href =
                  item.project_id && item.task_id
                    ? `/projects/${item.project_id}/tasks/${item.task_id}`
                    : "/projects";
                return (
                  <Link
                    className={[
                      "block border-b border-[rgba(9,30,66,0.06)] px-4 py-3 text-sm hover:bg-[#f7f8fa]",
                      item.read_at ? "bg-white" : "bg-[#f8fbff]",
                    ].join(" ")}
                    key={item.id}
                    onClick={() => {
                      setOpen(false);
                      void handleMarkRead(item);
                    }}
                    to={href}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-anywhere font-semibold text-[#172b4d]">
                        {item.title}
                      </p>
                      {item.priority === "important" ? (
                        <span className="rounded-full bg-[#fff4e5] px-2 py-0.5 text-[10px] font-semibold text-[#7f4c00]">
                          важно
                        </span>
                      ) : null}
                    </div>
                    {item.body ? (
                      <p className="text-anywhere mt-1 line-clamp-2 leading-6 text-[#44546f]">
                        {item.body}
                      </p>
                    ) : null}
                    <p className="mt-2 text-xs text-[#626f86]">
                      {formatDateTime(item.created_at)}
                    </p>
                  </Link>
                );
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export function Layout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user);

  async function handleLogout() {
    try {
      await authApi.logout();
    } finally {
      logout();
      startTransition(() => {
        navigate("/login", { replace: true });
      });
    }
  }

  const visibleNavItems = navItems.filter(
    (item) => !(item.href.startsWith("/admin") && user?.role !== "ADMIN"),
  );

  function closeDrawer() {
    setDrawerOpen(false);
  }

  const navContent = (
    <div className="flex h-full w-full min-w-0 flex-col">
      <div className="flex min-w-0 items-center justify-between gap-3">
        <Link className="block min-w-0" to="/" onClick={closeDrawer}>
          <div className="flex items-center gap-3">
            <span
              aria-hidden="true"
              className="grid h-10 w-10 place-items-center rounded-[12px] bg-[#172b4d] text-sm font-semibold text-white"
            >
              TP
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                Рабочая область
              </p>
              <h1 className="mt-1 truncate text-lg font-semibold text-[#172b4d]">
                Платформа задач
              </h1>
            </div>
          </div>
        </Link>
        <button
          className="ui-button-ghost px-3 py-2 text-xs font-semibold lg:hidden"
          onClick={closeDrawer}
          type="button"
        >
          Закрыть
        </button>
      </div>

      <nav
        aria-label="Основная навигация"
        className="mt-8 flex min-w-0 flex-1 flex-col gap-1.5"
      >
        {visibleNavItems.map((item) => (
          <NavLink
            key={item.href}
            className={({ isActive }) =>
              [
                "group block w-full min-w-0 overflow-hidden rounded-[12px] border px-4 py-3 text-sm transition-[background-color,color,border-color,box-shadow]",
                isActive
                  ? "border-[#bfd4f6] bg-[#e9f2ff] text-[#0c66e4] shadow-[inset_3px_0_0_#0c66e4]"
                  : "border-transparent text-[#44546f] hover:border-[rgba(9,30,66,0.1)] hover:bg-[#f7f8fa]",
              ].join(" ")
            }
            onClick={closeDrawer}
            to={item.href}
          >
            <span className="block truncate font-semibold">{item.label}</span>
            <span className="mt-1 block truncate text-xs text-[#626f86] group-hover:text-[#44546f]">
              {item.description}
            </span>
          </NavLink>
        ))}
      </nav>

      <NotificationCenter />

      <div className="min-w-0 space-y-3 rounded-[16px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4">
        <div className="flex items-center gap-3">
          <Avatar
            className="h-11 w-11 text-sm"
            imageUrl={user?.avatar_url}
            name={getUserDisplayName(user)}
          />
          <div className="min-w-0">
            <p className="truncate font-semibold text-[#172b4d]">
              {getUserDisplayName(user)}
            </p>
            <p className="truncate text-xs text-[#626f86]">
              {user?.full_name ?? "Неизвестный пользователь"}
            </p>
          </div>
        </div>
        <p className="break-all text-xs leading-5 text-[#44546f]">
          {user?.email}
        </p>
        <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
          {user?.role ? getRoleLabel(user.role) : "Роль не указана"}
        </p>
        <button
          className="ui-button-danger w-full justify-center"
          onClick={() => void handleLogout()}
          type="button"
        >
          Выйти
        </button>
      </div>
    </div>
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Перейти к основному содержимому
      </a>

      <div className="border-b border-[rgba(9,30,66,0.1)] bg-white px-4 py-3 md:px-6 lg:hidden">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <button
            className="ui-button-secondary px-3 py-2 text-xs font-semibold"
            onClick={() => setDrawerOpen(true)}
            type="button"
          >
            Меню
          </button>
          <div className="flex min-w-0 items-center gap-3">
            <div className="min-w-0 text-right">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                Профиль
              </p>
              <p className="truncate text-sm font-semibold text-[#172b4d]">
                {getUserDisplayName(user)}
              </p>
            </div>
            <Avatar
              className="h-10 w-10 text-sm"
              imageUrl={user?.avatar_url}
              name={getUserDisplayName(user)}
            />
          </div>
        </div>
      </div>

      {drawerOpen ? (
        <div
          className="fixed inset-0 z-50 bg-[rgba(9,30,66,0.24)] lg:hidden"
          onClick={closeDrawer}
        >
          <aside
            className="fixed inset-y-0 left-0 box-border w-[18rem] overflow-hidden border-r border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_24px_48px_rgba(9,30,66,0.18)]"
            onClick={(event) => event.stopPropagation()}
          >
            {navContent}
          </aside>
        </div>
      ) : null}

      <aside className="fixed inset-y-0 left-0 hidden box-border w-[17.5rem] overflow-hidden border-r border-[rgba(9,30,66,0.12)] bg-white px-5 py-6 lg:flex">
        {navContent}
      </aside>

      <main
        className="min-h-[calc(100svh-4.125rem)] min-w-0 px-4 py-4 sm:px-6 sm:py-6 lg:min-h-[100svh] lg:pl-[19.5rem] lg:pr-8"
        id="main-content"
      >
        <div className="mx-auto min-w-0 max-w-[1480px]">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
