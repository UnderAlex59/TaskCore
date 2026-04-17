import { startTransition, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { authApi } from "@/api/authApi";
import { Avatar } from "@/shared/components/Avatar";
import { getRoleLabel } from "@/shared/lib/locale";
import { getUserDisplayName } from "@/shared/lib/userProfile";
import { useAuthStore } from "@/store/authStore";

const navItems = [
  { href: "/projects", label: "Проекты" },
  { href: "/profile", label: "Профиль" },
  { href: "/admin/monitoring", label: "Администрирование" },
];

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
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-3">
        <button
          className="ui-button-danger px-3 py-2 text-xs font-bold uppercase tracking-[0.14em]"
          onClick={() => void handleLogout()}
          type="button"
        >
          Выйти
        </button>
        <button
          className="ui-button-ghost px-3 py-2 text-xs font-bold uppercase tracking-[0.14em] lg:hidden"
          onClick={closeDrawer}
          type="button"
        >
          Закрыть
        </button>
      </div>

      <Link className="mt-8 block" to="/" onClick={closeDrawer}>
        <p className="text-xs font-bold uppercase tracking-[0.22em] text-ember">
          Платформа задач
        </p>
        <h1 className="mt-3 text-2xl font-bold leading-tight text-ink">
          Требования, проверка и согласование в одном рабочем пространстве.
        </h1>
        <p className="mt-3 text-sm leading-7 text-slate/80">
          Единая среда для управления проектами, уточнения задач и обсуждения
          требований в чате.
        </p>
      </Link>

      <nav aria-label="Основная навигация" className="mt-10 flex flex-1 flex-col gap-2">
        {visibleNavItems.map((item) => (
          <NavLink
            key={item.href}
            className={({ isActive }) =>
              [
                "rounded-[10px] px-4 py-3 text-sm font-semibold transition-[background-color,color,border-color]",
                isActive
                  ? "bg-ember text-white shadow-soft"
                  : "border border-transparent text-ink/80 hover:border-black/10 hover:bg-white",
              ].join(" ")
            }
            onClick={closeDrawer}
            to={item.href}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="mt-8 border-t border-black/8 pt-4 text-sm text-slate">
        <div className="flex items-center gap-3">
          <Avatar
            className="h-11 w-11 text-sm"
            imageUrl={user?.avatar_url}
            name={getUserDisplayName(user)}
          />
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink">
              {getUserDisplayName(user)}
            </p>
            <p className="truncate text-xs text-slate/65">
              {user?.full_name ?? "Неизвестный пользователь"}
            </p>
          </div>
        </div>
        <p className="mt-1 break-all">{user?.email}</p>
        <p className="mt-3 text-xs font-bold uppercase tracking-[0.18em] text-ember">
          {user?.role ? getRoleLabel(user.role) : "Роль не указана"}
        </p>
      </div>
    </div>
  );

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Перейти к основному содержимому
      </a>

      <div className="border-b border-black/8 bg-white/80 px-4 py-3 backdrop-blur md:px-6 lg:hidden">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
          <button
            className="ui-button-secondary px-3 py-2 text-xs font-bold uppercase tracking-[0.14em]"
            onClick={() => setDrawerOpen(true)}
            type="button"
          >
            Меню
          </button>
          <div className="flex min-w-0 items-center gap-3">
            <div className="min-w-0 text-right">
              <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
                Рабочее пространство
              </p>
              <p className="truncate text-sm font-semibold text-ink">
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
          className="fixed inset-0 z-50 bg-ink/25 lg:hidden"
          onClick={closeDrawer}
        >
          <aside
            className="glass-panel fixed inset-y-0 left-0 w-[18rem] rounded-none border-r border-black/10 p-5 shadow-panel"
            onClick={(event) => event.stopPropagation()}
          >
            {navContent}
          </aside>
        </div>
      ) : null}

      <aside className="glass-panel fixed inset-y-0 left-0 hidden w-[18rem] rounded-none border-r border-black/10 p-5 shadow-none lg:flex">
        {navContent}
      </aside>

      <main
        className="min-h-[100svh] px-4 py-4 sm:px-6 sm:py-6 lg:pl-[20rem] lg:pr-8"
        id="main-content"
      >
        <div className="mx-auto max-w-7xl">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
