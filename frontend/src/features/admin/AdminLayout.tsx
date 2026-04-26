import { NavLink, Outlet } from "react-router-dom";

const adminNavItems = [
  { href: "/admin/monitoring", label: "Мониторинг" },
  { href: "/admin/llm-requests", label: "LLM-запросы" },
  { href: "/admin/validation-questions", label: "Вопросы валидации" },
  { href: "/admin/task-tags", label: "Теги задач" },
  { href: "/admin/providers", label: "Модельные профили" },
  { href: "/admin/vision-test", label: "Тест Vision" },
  { href: "/admin/agent-prompts", label: "Промпты агентов" },
  { href: "/admin/users", label: "Пользователи" },
];

export default function AdminLayout() {
  return (
    <section className="space-y-6">
      <header className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-6 sm:px-8">
        <p className="section-eyebrow">Administration</p>
        <h2 className="mt-3 text-3xl font-semibold text-[#172b4d] sm:text-4xl">
          Администрирование платформы
        </h2>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-[#44546f]">
          Мониторинг, модельные профили, правила маршрутизации и справочники
          платформы в одном рабочем пространстве.
        </p>
        <nav
          aria-label="Администрирование"
          className="mt-6 flex flex-wrap gap-2"
        >
          {adminNavItems.map((item) => (
            <NavLink
              key={item.href}
              className={({ isActive }) =>
                [
                  "rounded-[10px] border px-4 py-2.5 text-sm font-medium transition-[background-color,color,border-color]",
                  isActive
                    ? "border-[#bfd4f6] bg-[#e9f2ff] text-[#0c66e4]"
                    : "border-[rgba(9,30,66,0.1)] bg-[#fafbfc] text-[#44546f] hover:bg-white",
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
