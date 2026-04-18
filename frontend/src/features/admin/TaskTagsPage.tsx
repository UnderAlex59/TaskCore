import { useEffect, useState } from "react";

import { adminApi, type AdminTaskTagRead } from "@/api/adminApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";

export default function TaskTagsPage() {
  const [tags, setTags] = useState<AdminTaskTagRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [deletingTagId, setDeletingTagId] = useState<string | null>(null);
  const [editingTagId, setEditingTagId] = useState<string | null>(null);
  const [tagName, setTagName] = useState("");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [tagPendingDeletion, setTagPendingDeletion] =
    useState<AdminTaskTagRead | null>(null);

  async function loadTags() {
    try {
      setLoading(true);
      setError(null);
      setTags(await adminApi.listTaskTags());
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить справочник тегов."),
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadTags();
  }, []);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setSaving(true);
      setError(null);

      if (editingTagId) {
        const updatedTag = await adminApi.updateTaskTag(editingTagId, tagName);
        setTags((current) =>
          current
            .map((tag) => (tag.id === editingTagId ? updatedTag : tag))
            .sort((left, right) => left.name.localeCompare(right.name)),
        );
      } else {
        const createdTag = await adminApi.createTaskTag(tagName);
        setTags((current) =>
          [...current, createdTag].sort((left, right) =>
            left.name.localeCompare(right.name),
          ),
        );
      }

      setEditingTagId(null);
      setTagName("");
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось сохранить тег."));
    } finally {
      setSaving(false);
    }
  }

  function startEdit(tag: AdminTaskTagRead) {
    setEditingTagId(tag.id);
    setTagName(tag.name);
  }

  async function handleDelete() {
    if (!tagPendingDeletion) {
      return;
    }

    try {
      setDeletingTagId(tagPendingDeletion.id);
      setError(null);
      await adminApi.deleteTaskTag(tagPendingDeletion.id);
      setTags((current) =>
        current.filter((tag) => tag.id !== tagPendingDeletion.id),
      );
      setTagPendingDeletion(null);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить тег."));
    } finally {
      setDeletingTagId(null);
    }
  }

  const normalizedSearch = search.trim().toLocaleLowerCase();
  const filteredTags = normalizedSearch
    ? tags.filter((tag) =>
        tag.name.toLocaleLowerCase().includes(normalizedSearch),
      )
    : tags;

  if (loading) {
    return <LoadingSpinner label="Загрузка тегов задач" />;
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel rounded-[32px] border border-black/10 p-8 shadow-panel">
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-ember">
          Справочник тегов
        </p>
        <h2 className="mt-3 text-3xl font-extrabold text-ink sm:text-4xl">
          Теги задач
        </h2>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-ink/70">
          Администратор управляет справочными значениями тегов. Эти теги
          используются в задачах и в правилах проекта, поэтому свободный ввод
          больше не допускается.
        </p>
        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-2xl bg-ember/10 px-4 py-3 text-sm text-ember"
          >
            {error}
          </p>
        ) : null}
      </header>

      <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
        <form
          className="glass-panel space-y-4 rounded-[28px] border border-black/10 p-6 shadow-panel"
          onSubmit={handleSubmit}
        >
          <h3 className="text-xl font-bold text-ink">
            {editingTagId ? "Редактирование тега" : "Новый тег"}
          </h3>
          <label className="block">
            <span className="mb-2 block text-sm font-semibold text-ink/70">
              Название
            </span>
            <input
              autoComplete="off"
              className="ui-field"
              name="task-tag-name"
              onChange={(event) => setTagName(event.target.value)}
              placeholder="Например, Отчёты"
              required
              value={tagName}
            />
          </label>
          <p className="rounded-[10px] bg-black/5 px-4 py-3 text-sm text-slate/75">
            После переименования тега он обновится в уже существующих задачах и
            правилах проекта.
          </p>
          <div className="flex flex-wrap gap-3">
            <button
              className="ui-button-primary"
              disabled={saving}
              type="submit"
            >
              {saving
                ? "Сохраняем..."
                : editingTagId
                  ? "Обновить тег"
                  : "Создать тег"}
            </button>
            {editingTagId ? (
              <button
                className="ui-button-secondary"
                onClick={() => {
                  setEditingTagId(null);
                  setTagName("");
                }}
                type="button"
              >
                Отмена
              </button>
            ) : null}
          </div>
        </form>

        <section className="glass-panel rounded-[28px] border border-black/10 p-6 shadow-panel">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="text-xl font-bold text-ink">Доступные теги</h3>
              <p className="mt-1 text-sm text-slate/70">
                Поиск работает по названию тега.
              </p>
            </div>
            <label className="block sm:w-72">
              <span className="sr-only">Поиск по тегам</span>
              <input
                autoComplete="off"
                className="ui-field"
                name="task-tags-search"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Поиск тегов..."
                type="search"
                value={search}
              />
            </label>
          </div>

          <div className="mt-5 space-y-3">
            {filteredTags.length === 0 ? (
              <p className="rounded-[12px] border border-dashed border-black/10 px-4 py-5 text-sm text-slate/70">
                {tags.length === 0
                  ? "Справочник тегов пока пуст."
                  : "По текущему запросу ничего не найдено."}
              </p>
            ) : (
              filteredTags.map((tag) => (
                <article
                  key={tag.id}
                  className="rounded-[18px] border border-black/10 bg-white/80 p-4"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                    <div>
                      <h4 className="text-lg font-bold text-ink">{tag.name}</h4>
                      <p className="mt-2 text-sm text-slate/70">
                        Используется в задачах: {tag.tasks_count}. В правилах:{" "}
                        {tag.rules_count}.
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-3">
                      <button
                        className="ui-button-secondary"
                        onClick={() => startEdit(tag)}
                        type="button"
                      >
                        Изменить
                      </button>
                      <button
                        className="ui-button-danger"
                        onClick={() => setTagPendingDeletion(tag)}
                        type="button"
                      >
                        Удалить
                      </button>
                    </div>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>
      </div>

      <ConfirmDialog
        busy={deletingTagId === tagPendingDeletion?.id}
        confirmLabel="Удалить тег"
        description={
          tagPendingDeletion
            ? `Удалить тег «${tagPendingDeletion.name}» из справочника?`
            : ""
        }
        destructive
        onClose={() => setTagPendingDeletion(null)}
        onConfirm={handleDelete}
        open={tagPendingDeletion !== null}
        title="Удаление тега"
      />
    </section>
  );
}
