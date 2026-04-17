import { Link } from "react-router-dom";

import { useAuthStore } from "@/store/authStore";

const platformSignals = [
  { label: "Чат задачи", value: "Привязан к требованию" },
  { label: "Проверка", value: "До передачи в работу" },
  { label: "Изменения", value: "С понятным ревью" },
];

const featureRows = [
  {
    title: "Одна нить обсуждения для требования и всех решений по нему",
    body: "Чат живёт внутри самой задачи, поэтому аналитики и администраторы уточняют объём работ, не теряя контекст требования.",
  },
  {
    title: "Проверка начинается раньше, чем шум разработки",
    body: "Проверяйте требования, поднимайте открытые вопросы и не отдавайте команде в работу размытые черновики.",
  },
  {
    title: "Проекты, роли и настройки провайдеров остаются рядом с задачами",
    body: "Один интерфейс покрывает проектную работу, уточнение требований и административную маршрутизацию.",
  },
];

const workflowSteps = [
  {
    step: "01",
    title: "Зафиксируйте задачу",
    body: "Создайте проект, добавьте задачу и приложите исходное описание требования.",
  },
  {
    step: "02",
    title: "Уточните через чат",
    body: "Обсуждайте требование в чате задачи и подключайте конкретных агентов, когда нужен точечный разбор.",
  },
  {
    step: "03",
    title: "Проверьте и согласуйте",
    body: "Запустите проверку, рассмотрите предложения по изменениям и принимайте только те правки, которые усиливают задачу.",
  },
];

const faqItems = [
  {
    question: "Для кого эта система?",
    answer:
      "Текущий MVP рассчитан на аналитиков, администраторов, менеджеров и исполнителей, которым нужна единая точка для повышения качества требований до начала реализации.",
  },
  {
    question: "Чем чат отличается от обычного мессенджера?",
    answer:
      "Сообщения привязаны к конкретной задаче, поэтому обсуждение, предложения по изменениям и результаты проверки остаются частью одной рабочей истории.",
  },
  {
    question: "Могут ли администраторы управлять провайдерами?",
    answer:
      "Да. В админ-разделе доступны профили провайдеров, правила маршрутизации, мониторинг и управление пользователями.",
  },
  {
    question: "Что происходит, если проверка находит проблемы?",
    answer:
      "Пока задача находится в статусе черновика или доработки, её можно редактировать и уточнять, чтобы исправить требование до передачи в реализацию.",
  },
];

export default function LandingPage() {
  const user = useAuthStore((state) => state.user);

  const primaryHref = user ? "/projects" : "/register";
  const primaryLabel = user ? "Открыть рабочее пространство" : "Создать аккаунт";
  const secondaryHref = user ? "/projects" : "/login";
  const secondaryLabel = user ? "Перейти к проектам" : "Войти";

  return (
    <div className="app-shell">
      <header className="border-b border-black/8 bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div>
            <p className="section-eyebrow">Платформа задач</p>
            <p className="mt-1 text-sm text-slate/75">
              Русскоязычное рабочее пространство для уточнения и проверки задач.
            </p>
          </div>
          <nav className="hidden items-center gap-6 text-sm font-semibold text-slate/75 md:flex">
            <a className="hover:text-ink" href="#features">
              Возможности
            </a>
            <a className="hover:text-ink" href="#workflow">
              Процесс
            </a>
            <a className="hover:text-ink" href="#faq">
              Вопросы и ответы
            </a>
          </nav>
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

      <main>
        <section className="mx-auto grid max-w-7xl gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.15fr_0.85fr] lg:py-20">
          <div>
            <p className="section-eyebrow">Сначала качество требований</p>
            <h1 className="mt-4 max-w-4xl text-balance text-5xl font-bold leading-[1.02] text-ink sm:text-6xl">
              Держите задачу, обсуждение и историю согласований в одной
              управляемой среде.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-8 text-slate/80 sm:text-lg">
              Платформа создана для команд, которым нужен аккуратный приём
              задач, содержательный чат по требованиям, явное ревью изменений и
              интерфейс, ориентированный на работу, а не на декорации.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Link className="ui-button-primary" to={primaryHref}>
                {primaryLabel}
              </Link>
              <a className="ui-button-secondary" href="#workflow">
                Посмотреть процесс
              </a>
            </div>
          </div>

          <div className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
            <div className="grid gap-4 sm:grid-cols-3 lg:grid-cols-1">
              {platformSignals.map((item) => (
                <article
                  key={item.label}
                  className="border-b border-black/8 pb-4 last:border-b-0 last:pb-0"
                >
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-slate/55">
                    {item.label}
                  </p>
                  <p className="mt-2 text-lg font-bold text-ink">
                    {item.value}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6" id="features">
          <div className="border-t border-black/8 pt-10">
            <p className="section-eyebrow">Ключевые преимущества</p>
            <div className="mt-6 space-y-8">
              {featureRows.map((item) => (
                <article
                  key={item.title}
                  className="grid gap-4 border-b border-black/8 pb-8 last:border-b-0 last:pb-0 lg:grid-cols-[0.7fr_1.3fr]"
                >
                  <h2 className="text-2xl font-bold text-ink">{item.title}</h2>
                  <p className="max-w-3xl text-base leading-8 text-slate/80">
                    {item.body}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6" id="workflow">
          <div className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <p className="section-eyebrow">Как это работает</p>
                <h2 className="mt-3 text-3xl font-bold text-ink sm:text-4xl">
                  Три шага от постановки задачи до согласованной передачи в работу.
                </h2>
              </div>
              <p className="max-w-2xl text-sm leading-7 text-slate/75">
                Продукт устроен так, чтобы карточка задачи, рабочее обсуждение и
                путь согласования оставались в одном потоке.
              </p>
            </div>
            <div className="mt-8 grid gap-6 lg:grid-cols-3">
              {workflowSteps.map((item) => (
                <article
                  key={item.step}
                  className="rounded-[10px] border border-black/10 bg-white/70 p-5"
                >
                  <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
                    {item.step}
                  </p>
                  <h3 className="mt-3 text-xl font-bold text-ink">
                    {item.title}
                  </h3>
                  <p className="mt-3 text-sm leading-7 text-slate/80">
                    {item.body}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-10 sm:px-6" id="faq">
          <div className="border-t border-black/8 pt-10">
            <p className="section-eyebrow">Вопросы и ответы</p>
            <div className="mt-6 grid gap-4">
              {faqItems.map((item) => (
                <details
                  key={item.question}
                  className="glass-panel border border-black/10 p-5 shadow-soft"
                >
                  <summary className="cursor-pointer list-none text-lg font-bold text-ink">
                    {item.question}
                  </summary>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-slate/80">
                    {item.answer}
                  </p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-7xl px-4 py-14 sm:px-6">
          <div className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
            <p className="section-eyebrow">Начало работы</p>
            <div className="mt-4 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h2 className="text-3xl font-bold text-ink sm:text-4xl">
                  Откройте рабочее пространство и ведите задачу в одном потоке.
                </h2>
                <p className="mt-3 max-w-2xl text-sm leading-7 text-slate/80">
                  Начните с обзорной страницы, а затем переходите к проектам,
                  уточнению задач, проверке и управляемому рассмотрению изменений.
                </p>
              </div>
              <div className="flex flex-wrap gap-3">
                <Link className="ui-button-primary" to={primaryHref}>
                  {primaryLabel}
                </Link>
                <Link className="ui-button-secondary" to={secondaryHref}>
                  {secondaryLabel}
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
