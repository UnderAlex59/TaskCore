import { startTransition, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { projectsApi, type ProjectRead } from "@/api/projectsApi";
import { taskTagsApi, type TaskTagOption } from "@/api/taskTagsApi";
import { tasksApi } from "@/api/tasksApi";
import { buildTaskDocumentFromEditors } from "@/features/tasks/taskDocument";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import TagMultiSelect from "@/shared/components/TagMultiSelect";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { useAuthStore } from "@/store/authStore";

const TASK_CREATORS = new Set(["ADMIN", "ANALYST"]);

export default function TaskCreatePage() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);

  const [project, setProject] = useState<ProjectRead | null>(null);
  const [taskTags, setTaskTags] = useState<TaskTagOption[]>([]);
  const [title, setTitle] = useState("");
  const [documentBody, setDocumentBody] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canCreateTask = TASK_CREATORS.has(user?.role ?? "");
  const tasksHref = projectId ? `/projects/${projectId}/tasks` : "/projects";
  const hasTitle = title.trim().length > 0;
  const hasDraftContent =
    hasTitle || documentBody.trim().length > 0 || tags.length > 0;

  useEffect(() => {
    let cancelled = false;

    async function loadData() {
      if (!projectId) {
        setError("Не найден идентификатор проекта.");
        setLoading(false);
        return;
      }

      try {
        setLoading(true);
        setError(null);
        const [loadedProject, loadedTaskTags] = await Promise.all([
          projectsApi.get(projectId),
          taskTagsApi.list(projectId),
        ]);

        if (!cancelled) {
          setProject(loadedProject);
          setTaskTags(loadedTaskTags);
        }
      } catch (caught) {
        if (!cancelled) {
          setError(
            getApiErrorMessage(
              caught,
              "Не удалось загрузить данные для создания задачи.",
            ),
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadData();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function handleCreateTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || creating) {
      return;
    }

    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("Укажите название задачи.");
      return;
    }

    try {
      setCreating(true);
      setError(null);
      const content = documentBody.trim()
        ? buildTaskDocumentFromEditors(documentBody, "")
        : "";
      const created = await tasksApi.create(projectId, {
        title: trimmedTitle,
        content,
        tags: tags.filter(Boolean),
      });

      startTransition(() => {
        navigate(`/projects/${projectId}/tasks/${created.id}`);
      });
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось создать задачу."));
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка формы создания задачи" />;
  }

  if (!canCreateTask) {
    return (
      <section className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-6">
        <div className="flex flex-wrap items-center gap-2 text-sm text-[#626f86]">
          <Link className="hover:text-[#0c66e4]" to={tasksHref}>
            Задачи
          </Link>
          <span>/</span>
          <span>Новая задача</span>
        </div>
        <h2 className="mt-4 text-2xl font-semibold text-[#172b4d]">
          Создание задачи недоступно
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-7 text-[#44546f]">
          Новые задачи могут создавать аналитики и администраторы проекта.
        </p>
      </section>
    );
  }

  return (
    <form className="space-y-5" onSubmit={handleCreateTask}>
      <header className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
        <div className="flex flex-col gap-5">
          <div className="flex flex-wrap items-center gap-2 text-sm text-[#626f86]">
            <Link className="hover:text-[#0c66e4]" to={tasksHref}>
              Задачи
            </Link>
            <span>/</span>
            <span>Новая задача</span>
          </div>

          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div className="min-w-0">
              <p className="section-eyebrow">Рабочая область задачи</p>
              <h2 className="mt-2 text-balance text-3xl font-semibold leading-tight text-[#172b4d] sm:text-[2.25rem]">
                Новая задача
              </h2>
              <p className="mt-3 max-w-4xl text-sm leading-7 text-[#44546f]">
                Работайте над постановкой сразу в полном пространстве: название,
                документ задачи и теги доступны до первого сохранения.
              </p>
            </div>

            <Link className="ui-button-secondary" to={tasksHref}>
              Вернуться к списку
            </Link>
          </div>

          <div className="flex flex-wrap gap-2 text-xs font-medium text-[#44546f]">
            <span className="rounded-full bg-[#e9f2ff] px-3 py-1.5 text-[#0c66e4]">
              Черновик
            </span>
            <span className="rounded-full bg-[#f7f8fa] px-3 py-1.5">
              {project?.name ?? "Проект"}
            </span>
            <span className="rounded-full bg-[#f7f8fa] px-3 py-1.5">
              Создается после сохранения
            </span>
          </div>
        </div>
      </header>

      {error ? (
        <p
          aria-live="polite"
          className="rounded-[14px] border border-[rgba(174,46,36,0.16)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]"
        >
          {error}
        </p>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.8fr)_320px] xl:items-start">
        <section className="overflow-hidden rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_1px_2px_rgba(9,30,66,0.06),0_12px_32px_rgba(9,30,66,0.05)]">
          <div className="border-b border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-6 py-4">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
              Документ задачи
            </p>
            <p className="mt-2 text-sm leading-6 text-[#44546f]">
              Оформите постановку как единый документ. После создания откроются
              проверка, вложения, история изменений и рабочий чат.
            </p>
          </div>

          <div className="space-y-6 px-6 py-6 sm:px-8 sm:py-8">
            <label className="block">
              <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                Название задачи
              </span>
              <input
                autoComplete="off"
                className="w-full border-0 border-b border-[rgba(9,30,66,0.14)] bg-transparent px-0 py-2 text-[2rem] font-semibold leading-tight text-[#172b4d] outline-none transition-colors placeholder:text-[#97a0af] focus:border-[#0c66e4] focus:ring-0"
                name="task-title"
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Например, уточнить критерии приемки"
                required
                value={title}
              />
            </label>

            <label className="block">
              <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
                Текст задачи
              </span>
              <textarea
                className="min-h-[36rem] w-full resize-y rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-4 text-[15px] leading-8 text-[#172b4d] outline-none transition-colors placeholder:text-[#97a0af] focus:border-[#0c66e4] focus:ring-4 focus:ring-[#dbeafe]"
                name="task-document"
                onChange={(event) => setDocumentBody(event.target.value)}
                placeholder="Опишите задачу как единый документ. Можно использовать заголовки, списки, бизнес-правила и критерии приемки."
                value={documentBody}
              />
            </label>
          </div>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-6">
          <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Состояние
            </p>
            <p className="mt-3 text-sm leading-7 text-[#44546f]">
              Пока задача не сохранена, она остается локальным черновиком на
              странице. Создание откроет полноценную карточку задачи без
              повторного ввода.
            </p>
          </section>

          <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
            <TagMultiSelect
              helperText={
                taskTags.length === 0
                  ? "Администратор еще не добавил теги в справочник."
                  : "Теги используются для правил, валидации и поиска связанных задач."
              }
              label="Теги"
              name="task-tags"
              noOptionsLabel="Справочник тегов пока пуст"
              onChange={setTags}
              options={taskTags}
              placeholder="Выберите теги"
              searchPlaceholder="Найти тег"
              value={tags}
            />
          </section>

          <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              После сохранения
            </p>
            <ul className="mt-3 space-y-3 text-sm leading-6 text-[#44546f]">
              <li>Задача появится в списке проекта.</li>
              <li>Откроются проверка требований и загрузка вложений.</li>
              <li>Аналитик продолжит работу в этой же структуре документа.</li>
            </ul>
          </section>
        </aside>
      </div>

      <div className="sticky bottom-3 z-10 flex flex-col gap-4 rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-4 shadow-[0_12px_24px_rgba(9,30,66,0.08)] sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <p className="text-sm font-medium text-[#172b4d]">
            {hasDraftContent
              ? hasTitle
                ? "Черновик готов к сохранению."
                : "Укажите название задачи."
              : "Заполните название и текст задачи."}
          </p>
          <p className="text-xs text-[#626f86]">
            После создания откроется рабочая страница задачи.
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <Link className="ui-button-secondary" to={tasksHref}>
            Отмена
          </Link>
          <button
            className="ui-button-primary min-w-[10rem]"
            disabled={creating || !hasTitle}
            type="submit"
          >
            {creating ? "Создаем..." : "Создать задачу"}
          </button>
        </div>
      </div>
    </form>
  );
}
