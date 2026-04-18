import { useEffect, useState } from "react";

import type { TaskTagOption } from "@/api/taskTagsApi";
import type { TaskRead, TaskUpdate } from "@/api/tasksApi";
import TagMultiSelect from "@/shared/components/TagMultiSelect";

interface Props {
  availableTags: TaskTagOption[];
  canCommitChanges?: boolean;
  committing?: boolean;
  disabled?: boolean;
  embeddingsStale?: boolean;
  loading?: boolean;
  onCommit?: () => Promise<void>;
  onSubmit: (payload: TaskUpdate) => Promise<void>;
  task: TaskRead;
}

function haveSameTags(left: string[], right: string[]) {
  return (
    left.length === right.length &&
    left.every((tag, index) => tag === right[index])
  );
}

export default function TaskForm({
  task,
  availableTags,
  canCommitChanges = false,
  committing = false,
  onSubmit,
  onCommit,
  disabled = false,
  embeddingsStale = false,
  loading = false,
}: Props) {
  const [title, setTitle] = useState(task.title);
  const [content, setContent] = useState(task.content);
  const [tags, setTags] = useState(task.tags);

  useEffect(() => {
    setTitle(task.title);
    setContent(task.content);
    setTags(task.tags);
  }, [task]);

  const hasUnsavedChanges =
    title !== task.title ||
    content !== task.content ||
    !haveSameTags(tags, task.tags);
  const isPostApprovalFlow = ["ready_for_dev", "in_progress", "done"].includes(
    task.status,
  );
  const isAwaitingApproval = task.status === "awaiting_approval";
  const saveDisabled = disabled || loading || !hasUnsavedChanges;
  const commitDisabled =
    !canCommitChanges || committing || hasUnsavedChanges || !embeddingsStale;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({
      title,
      content,
      tags,
    });
  }

  return (
    <form className="space-y-6" onSubmit={handleSubmit}>
      <div className="flex flex-col gap-3 border-b border-black/8 pb-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="section-eyebrow">Редактор аналитика</p>
            <h3 className="mt-2 text-2xl font-bold text-ink sm:text-3xl">
              Рабочая версия требования
            </h3>
            <p className="mt-3 text-sm leading-7 text-slate/75">
              Пространство для полноценной правки постановки задачи. После
              передачи в разработку текст сохраняется сразу, а пересчет
              эмбеддингов запускается отдельным явным commit.
            </p>
          </div>
          <div className="rounded-[14px] border border-black/10 bg-slate-50/70 px-4 py-3 text-sm text-slate/75">
            <p className="font-semibold text-ink">Статус редактора</p>
            <p className="mt-1">
              {disabled
                ? "Изменения временно недоступны."
                : hasUnsavedChanges
                  ? "Есть несохраненные правки."
                  : embeddingsStale && canCommitChanges
                    ? "Текст сохранен, но эмбеддинги еще не обновлены."
                    : "Редактор синхронизирован с текущей задачей."}
            </p>
          </div>
        </div>
        {isAwaitingApproval ? (
          <p className="rounded-[12px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            Любое изменение на этапе approve вернет задачу в доработку и
            потребует повторной проверки.
          </p>
        ) : null}
        {isPostApprovalFlow ? (
          <p className="rounded-[12px] border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900">
            После старта разработки правки сохраняются в карточке задачи сразу,
            но чат, поиск похожих задач и RAG-контекст увидят новую версию
            только после commit.
          </p>
        ) : null}
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.7fr)_minmax(280px,0.9fr)] xl:items-start">
        <div className="space-y-5">
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Название
            </span>
            <input
              className="ui-field px-5 py-4 text-lg sm:text-lg"
              disabled={disabled}
              name="task-title"
              onChange={(event) => setTitle(event.target.value)}
              value={title}
            />
          </label>

          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Текст требования
            </span>
            <textarea
              className="ui-field min-h-[30rem] resize-y px-5 py-5 text-[15px] leading-8 xl:min-h-[38rem]"
              disabled={disabled}
              name="task-content"
              onChange={(event) => setContent(event.target.value)}
              value={content}
            />
          </label>
        </div>

        <aside className="space-y-5 rounded-[16px] border border-black/10 bg-slate-50/70 p-5">
          <div>
            <p className="text-sm font-semibold text-ink">Контур публикации</p>
            <p className="mt-2 text-sm leading-7 text-slate/75">
              Сначала сохраните текст в карточку задачи, затем выполните
              отдельный commit, чтобы база пересчитала эмбеддинги и обновила
              контекст для агентов.
            </p>
          </div>

          <TagMultiSelect
            disabled={disabled}
            helperText={
              availableTags.length === 0
                ? "Администратор еще не добавил теги в справочник."
                : "Можно выбрать несколько тегов из справочника."
            }
            label="Теги"
            name="task-tags"
            noOptionsLabel="Справочник тегов пока пуст"
            onChange={setTags}
            options={availableTags}
            placeholder="Выберите теги"
            searchPlaceholder="Найти тег"
            value={tags}
          />

          <div className="rounded-[14px] border border-black/10 bg-white/80 p-4">
            <p className="text-sm font-semibold text-ink">Что увидит команда</p>
            <p className="mt-2 text-sm leading-7 text-slate/75">
              Карточка задачи показывает последние сохраненные формулировки.
              Commit синхронизирует их с поиском похожих задач, валидатором и
              агентами.
            </p>
          </div>
        </aside>
      </div>

      <div className="sticky bottom-3 z-10 flex flex-col gap-4 rounded-[16px] border border-black/10 bg-white/95 p-4 shadow-panel backdrop-blur sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-slate/75">
          {hasUnsavedChanges
            ? "Есть несохраненные изменения в редакторе."
            : embeddingsStale && canCommitChanges
              ? "Изменения сохранены. Нажмите commit, чтобы пересчитать эмбеддинги."
              : isPostApprovalFlow
                ? "После сохранения используйте commit для публикации новой семантической версии задачи."
                : "Сохранение обновляет задачу и рабочий контекст аналитика."}
        </p>
        <div className="flex flex-wrap gap-3">
          {canCommitChanges ? (
            <button
              className="ui-button-secondary"
              disabled={commitDisabled}
              onClick={() => void onCommit?.()}
              type="button"
            >
              {committing ? "Коммитим изменения..." : "Commit изменений"}
            </button>
          ) : null}
          <button
            className="ui-button-primary"
            disabled={saveDisabled}
            type="submit"
          >
            {loading ? "Сохраняем..." : "Сохранить задачу"}
          </button>
        </div>
      </div>
    </form>
  );
}
