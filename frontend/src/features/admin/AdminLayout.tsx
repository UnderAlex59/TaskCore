import { NavLink, Outlet } from "react-router-dom";

const adminNavItems = [
  { href: "/admin/monitoring", label: "Мониторинг" },
  { href: "/admin/providers", label: "Провайдеры" },
  { href: "/admin/users", label: "Пользователи" },
];

export default function AdminLayout() {
  return (
    <section className="space-y-6">
      <header className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
        <p className="section-eyebrow">Администрирование</p>
        <h2 className="mt-3 text-3xl font-bold text-ink sm:text-4xl">
          Управление системой и операциями
        </h2>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate/80">
          Управляйте профилями провайдеров, настраивайте маршрутизацию LLM,
          смотрите использование системы и храните аудит критичных действий.
        </p>
        <nav aria-label="Администрирование" className="mt-6 flex flex-wrap gap-2">
          {adminNavItems.map((item) => (
            <NavLink
              key={item.href}
              className={({ isActive }) =>
                [
                  "rounded-[10px] px-4 py-2.5 text-sm font-semibold transition-[background-color,color,box-shadow]",
                  isActive
                    ? "bg-ember text-white"
                    : "bg-white/70 text-ink hover:bg-white",
                ].join(" ")
              }
              to={item.href}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <Outlet />
    </section>
  );
}
