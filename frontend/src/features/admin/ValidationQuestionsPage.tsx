import {
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useState,
} from "react";
import { Link } from "react-router-dom";

import {
  adminApi,
  type ValidationQuestionPageRead,
} from "@/api/adminApi";
import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import type { TaskStatus, ValidationResult } from "@/api/tasksApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import {
  formatDateTimeFull,
  getTaskStatusLabel,
  getValidationVerdictLabel,
} from "@/shared/lib/locale";

const PAGE_SIZE = 20;
const TASK_STATUS_OPTIONS: TaskStatus[] = [
  "draft",
  "validating",
  "needs_rework",
  "awaiting_approval",
  "ready_for_dev",
  "in_progress",
  "done",
];
const VERDICT_OPTIONS: ValidationResult["verdict"][] = [
  "needs_rework",
  "approved",
];

export default function ValidationQuestionsPage() {
  const [questionsPage, setQuestionsPage] = useState<ValidationQuestionPageRead | null>(null);
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteCandidate, setDeleteCandidate] =
    useState<ValidationQuestionPageRead["items"][number] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [projectId, setProjectId] = useState("all");
  const [taskStatus, setTaskStatus] = useState<TaskStatus | "all">("all");
  const [verdict, setVerdict] = useState<ValidationResult["verdict"] | "all">("all");
  const [tag, setTag] = useState("");
  const [search, setSearch] = useState("");

  const deferredSearch = useDeferredValue(search.trim());
  const deferredTag = useDeferredValue(tag.trim());

  async function loadProjects() {
    try {
      const loadedProjects = await projectsApi.list();
      setProjects(loadedProjects);
    } catch {
      setProjects([]);
    }
  }

  async function loadQuestions() {
    try {
      setLoading(true);
      setError(null);
      const payload = await adminApi.listValidationQuestions({
        page,
        size: PAGE_SIZE,
        ...(projectId !== "all" ? { project_id: projectId } : {}),
        ...(taskStatus !== "all" ? { task_status: taskStatus } : {}),
        ...(verdict !== "all" ? { verdict } : {}),
        ...(deferredTag ? { tag: deferredTag } : {}),
        ...(deferredSearch ? { search: deferredSearch } : {}),
      });
      setQuestionsPage(payload);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить вопросы для валидации."));
    } finally {
      setLoading(false);
    }
  }

  const onLoadQuestions = useEffectEvent(loadQuestions);
  const onLoadProjects = useEffectEvent(loadProjects);

  useEffect(() => {
    void onLoadProjects();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    void onLoadQuestions();
  }, [page, projectId, taskStatus, verdict, deferredTag, deferredSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalPages = questionsPage
    ? Math.max(1, Math.ceil(questionsPage.total / questionsPage.page_size))
    : 1;

  async function handleDeleteConfirmed() {
    if (!deleteCandidate) {
      return;
    }

    try {
      setDeletingId(deleteCandidate.id);
      setError(null);
      await adminApi.deleteValidationQuestion(deleteCandidate.id);
      setDeleteCandidate(null);
      await loadQuestions();
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить вопрос."));
    } finally {
      setDeletingId(null);
    }
  }

  function resetFilters() {
    setProjectId("all");
    setTaskStatus("all");
    setVerdict("all");
    setTag("");
    setSearch("");
    setPage(1);
  }

  function changePage(nextPage: number) {
    setPage(Math.min(Math.max(nextPage, 1), totalPages));
  }

  if (loading && !questionsPage) {
    return <LoadingSpinner label="Загрузка вопросов для валидации" />;
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
              База вопросов
            </p>
            <h3 className="mt-2 text-2xl font-extrabold text-ink sm:text-3xl">
              Пул вопросов для разбора
            </h3>
            <p className="mt-3 max-w-3xl text-sm leading-7 text-ink/70">
              Здесь собраны вопросы работников из чата задачи, на которые
              ассистент не смог уверенно ответить по знаниям проекта и задачи.
              Можно быстро отфильтровать их по проекту, статусу и вердикту,
              а лишние записи удалить.
            </p>
          </div>
          <div className="rounded-3xl bg-white/70 px-5 py-4 text-right shadow-soft">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ink/45">
              Всего открытых записей
            </p>
            <p className="mt-2 text-3xl font-extrabold text-ink">
              {questionsPage?.total ?? 0}
            </p>
          </div>
        </div>

        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember"
          >
            {error}
          </p>
        ) : null}
      </header>

      <section className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Фильтры
            </p>
            <h4 className="mt-2 text-xl font-extrabold text-ink">
              Отбор по контексту задачи
            </h4>
          </div>
          <button className="ui-button-secondary" onClick={resetFilters} type="button">
            Сбросить фильтры
          </button>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">Проект</span>
            <select
              className="ui-field"
              onChange={(event) => {
                setProjectId(event.target.value);
                setPage(1);
              }}
              value={projectId}
            >
              <option value="all">Все проекты</option>
              {projects.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">Статус задачи</span>
            <select
              className="ui-field"
              onChange={(event) => {
                setTaskStatus(event.target.value as TaskStatus | "all");
                setPage(1);
              }}
              value={taskStatus}
            >
              <option value="all">Все статусы</option>
              {TASK_STATUS_OPTIONS.map((status) => (
                <option key={status} value={status}>
                  {getTaskStatusLabel(status)}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">Вердикт</span>
            <select
              className="ui-field"
              onChange={(event) => {
                setVerdict(event.target.value as ValidationResult["verdict"] | "all");
                setPage(1);
              }}
              value={verdict}
            >
              <option value="all">Все вердикты</option>
              {VERDICT_OPTIONS.map((item) => (
                <option key={item} value={item}>
                  {getValidationVerdictLabel(item)}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">Тег</span>
            <input
              className="ui-field"
              onChange={(event) => {
                setTag(event.target.value);
                setPage(1);
              }}
              placeholder="reports"
              value={tag}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">Поиск</span>
            <input
              className="ui-field"
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Критерии приёмки"
              value={search}
            />
          </label>
        </div>
      </section>

      <div className="space-y-4">
        {questionsPage?.items.length ? (
          questionsPage.items.map((item) => (
            <article
              className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel"
              key={item.id}
            >
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-ink/50">
                    <span>{item.project_name}</span>
                    <span className="rounded-full bg-ember/10 px-3 py-1 text-ember">
                      {getValidationVerdictLabel(item.validation_verdict)}
                    </span>
                    <span className="rounded-full bg-ink/5 px-3 py-1 text-ink/70">
                      {getTaskStatusLabel(item.task_status)}
                    </span>
                  </div>
                  <h4 className="mt-3 text-xl font-extrabold text-ink">
                    <Link
                      className="transition-colors hover:text-ember"
                      to={`/projects/${item.project_id}/tasks/${item.task_id}`}
                    >
                      {item.task_title}
                    </Link>
                  </h4>
                  <p className="mt-4 max-w-4xl text-sm leading-7 text-ink/80">
                    {item.question_text}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {item.tags.length ? (
                      item.tags.map((taskTag) => (
                        <span
                          className="rounded-full bg-ink/5 px-3 py-1 text-xs font-semibold text-ink/70"
                          key={taskTag}
                        >
                          #{taskTag}
                        </span>
                      ))
                    ) : (
                      <span className="rounded-full bg-ink/5 px-3 py-1 text-xs font-semibold text-ink/50">
                        Без тегов
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex flex-col items-start gap-3 xl:items-end">
                  <div className="text-sm text-ink/60">
                    <p>Проверено: {item.validated_at ? formatDateTimeFull(item.validated_at) : "н/д"}</p>
                    <p>Добавлено: {formatDateTimeFull(item.created_at)}</p>
                  </div>
                  <button
                    aria-label={`Удалить вопрос ${item.task_title}`}
                    className="ui-button-danger"
                    onClick={() => setDeleteCandidate(item)}
                    type="button"
                  >
                    Удалить
                  </button>
                </div>
              </div>
            </article>
          ))
        ) : (
          <section className="glass-panel rounded-[28px] border border-dashed border-black/10 p-10 text-center shadow-panel">
            <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
              Очередь пуста
            </p>
            <h4 className="mt-2 text-2xl font-extrabold text-ink">
              Под выбранные фильтры вопросов не найдено
            </h4>
            <p className="mt-3 text-sm leading-7 text-ink/70">
              Попробуйте ослабить фильтры или сбросить поиск, чтобы увидеть
              другие записи из базы вопросов валидации.
            </p>
          </section>
        )}
      </div>

      <footer className="flex items-center justify-between gap-4">
        <p className="text-sm text-ink/60">
          Страница {questionsPage?.page ?? 1} из {totalPages}
        </p>
        <div className="flex gap-3">
          <button
            className="ui-button-secondary"
            disabled={(questionsPage?.page ?? 1) <= 1}
            onClick={() => changePage((questionsPage?.page ?? 1) - 1)}
            type="button"
          >
            Назад
          </button>
          <button
            className="ui-button-secondary"
            disabled={(questionsPage?.page ?? 1) >= totalPages}
            onClick={() => changePage((questionsPage?.page ?? 1) + 1)}
            type="button"
          >
            Дальше
          </button>
        </div>
      </footer>

      <ConfirmDialog
        busy={deletingId === deleteCandidate?.id}
        confirmLabel="Удалить"
        description={
          deleteCandidate
            ? "Вопрос исчезнет из админского списка и из сохранённого результата валидации по задаче."
            : ""
        }
        destructive
        onClose={() => {
          if (!deletingId) {
            setDeleteCandidate(null);
          }
        }}
        onConfirm={() => void handleDeleteConfirmed()}
        open={deleteCandidate !== null}
        title="Удалить вопрос валидации?"
      />
    </section>
  );
}
