import { Link } from "react-router-dom";

import { useAuthStore } from "@/store/authStore";

const productHighlights = [
  {
    title: "Требования в одном контуре",
    body: "Постановка, уточнения, проверка, материалы и история изменений живут внутри одной задачи.",
  },
  {
    title: "Командная передача без потери контекста",
    body: "После согласования задача уходит в разработку вместе с полным рабочим контекстом и сохраненными решениями.",
  },
  {
    title: "Управляемый change flow",
    body: "Изменения после старта разработки сохраняются отдельно и публикуются в семантический индекс через явный commit.",
  },
];

const workflowRows = [
  {
    title: "Создайте проект и постановку",
    body: "Оформите задачу как структурированный документ, добавьте участников и зафиксируйте исходный контекст.",
  },
  {
    title: "Пройдите проверку и согласование",
    body: "Запустите валидацию, устраните замечания и подтвердите задачу до передачи в реализацию.",
  },
  {
    title: "Ведите задачу в одном рабочем потоке",
    body: "Обсуждение, review артефакты и последующие уточнения остаются частью той же истории задачи.",
  },
];

export default function LandingPage() {
  const user = useAuthStore((state) => state.user);

  const primaryHref = user ? "/projects" : "/register";
  const primaryLabel = user ? "Открыть проекты" : "Создать аккаунт";
  const secondaryHref = user ? "/profile" : "/login";
  const secondaryLabel = user ? "Профиль" : "Войти";

  return (
    <div className="min-h-[100svh] bg-[#f5f6f8]">
      <header className="border-b border-[rgba(9,30,66,0.08)] bg-white">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
              Task Platform
            </p>
            <p className="mt-1 text-sm text-[#44546f]">
              Рабочая система для требований, проверки и командной передачи
              задач.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              className="ui-button-ghost hidden sm:inline-flex"
              to={secondaryHref}
            >
              {secondaryLabel}
            </Link>
            <Link className="ui-button-primary" to={primaryHref}>
              {primaryLabel}
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
        <section className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white">
          <div className="grid gap-10 px-6 py-8 lg:grid-cols-[minmax(0,1.2fr)_320px] lg:px-8 lg:py-10">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                Product Workspace
              </p>
              <h1 className="mt-4 max-w-4xl text-4xl font-semibold leading-tight text-[#172b4d] sm:text-5xl">
                Управляйте жизненным циклом задачи как единым рабочим
                документом.
              </h1>
              <p className="mt-5 max-w-3xl text-base leading-8 text-[#44546f]">
                Платформа объединяет постановку, проверку, обсуждение и передачу
                задачи в разработку. Интерфейс ориентирован на рабочий процесс
                команды, а не на витринную демонстрацию функций.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link className="ui-button-primary" to={primaryHref}>
                  {primaryLabel}
                </Link>
                <Link className="ui-button-secondary" to={secondaryHref}>
                  {secondaryLabel}
                </Link>
              </div>
            </div>

            <aside className="rounded-[18px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                Подход
              </p>
              <div className="mt-4 space-y-4">
                <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                    Структура
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#172b4d]">
                    Задача оформляется как рабочая страница, а не как
                    разрозненная карточка.
                  </p>
                </div>
                <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                    Контроль
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#172b4d]">
                    Изменения после старта разработки публикуются в индекс
                    только через commit.
                  </p>
                </div>
                <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                    Команда
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#172b4d]">
                    Аналитик, разработчик и тестировщик работают в одной истории
                    задачи.
                  </p>
                </div>
              </div>
            </aside>
          </div>
        </section>

        <section className="mt-6 grid gap-4 lg:grid-cols-3">
          {productHighlights.map((item) => (
            <article
              key={item.title}
              className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-5"
            >
              <h2 className="text-xl font-semibold text-[#172b4d]">
                {item.title}
              </h2>
              <p className="mt-3 text-sm leading-7 text-[#44546f]">
                {item.body}
              </p>
            </article>
          ))}
        </section>

        <section className="mt-6 rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-8 lg:px-8">
          <div className="grid gap-8 lg:grid-cols-[280px_minmax(0,1fr)]">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                Рабочий процесс
              </p>
              <h2 className="mt-3 text-3xl font-semibold leading-tight text-[#172b4d]">
                От постановки до передачи в работу без переключения контекста.
              </h2>
            </div>
            <div className="space-y-6">
              {workflowRows.map((item, index) => (
                <article
                  key={item.title}
                  className="grid gap-4 border-t border-[rgba(9,30,66,0.08)] pt-6 first:border-t-0 first:pt-0 md:grid-cols-[72px_minmax(0,1fr)]"
                >
                  <div className="text-2xl font-semibold text-[#97a0af]">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div>
                    <h3 className="text-xl font-semibold text-[#172b4d]">
                      {item.title}
                    </h3>
                    <p className="mt-2 text-sm leading-7 text-[#44546f]">
                      {item.body}
                    </p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
