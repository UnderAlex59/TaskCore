import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import type { TaskTagOption } from "@/api/taskTagsApi";
import type {
  TaskAttachmentRead,
  TaskRead,
  TaskTagSuggestionResponse,
  TaskUpdate,
} from "@/api/tasksApi";
import AttachmentUpload from "@/features/tasks/AttachmentUpload";
import TaskMarkdownPreview from "@/features/tasks/TaskMarkdownPreview";
import {
  buildTaskDocumentFromEditors,
  normalizeTaskEditorValue,
  parseTaskDocument,
  serializeTaskBodyForEditor,
} from "@/features/tasks/taskDocument";
import TagMultiSelect from "@/shared/components/TagMultiSelect";
import { formatDateTime, getTaskStatusLabel } from "@/shared/lib/locale";

interface Props {
  activePane?: "document" | "history";
  attachments?: TaskAttachmentRead[];
  attachmentsUploading?: boolean;
  availableTags: TaskTagOption[];
  canCommitChanges?: boolean;
  canSuggestTags?: boolean;
  committing?: boolean;
  disabled?: boolean;
  embeddingsStale?: boolean;
  loading?: boolean;
  onCommit?: () => Promise<void>;
  onSuggestTags?: (payload: {
    title: string;
    content: string;
    current_tags: string[];
  }) => Promise<TaskTagSuggestionResponse>;
  onDeleteAttachment?: (attachment: TaskAttachmentRead) => Promise<void>;
  onOpenAttachment?: (attachment: TaskAttachmentRead) => Promise<Blob>;
  onSubmit: (payload: TaskUpdate) => Promise<void>;
  onUploadAttachment?: (file: File) => Promise<void>;
  suggestingTags?: boolean;
  task: TaskRead;
}

const MARKDOWN_TABLE_TEMPLATE =
  "| Поле | Правило |\n|---|---|\n| Статус | Обязателен |\n| Дата | Не раньше текущей |";

function haveSameTags(left: string[], right: string[]) {
  return (
    left.length === right.length &&
    left.every((tag, index) => tag === right[index])
  );
}

function EditorCard({
  children,
  helperText,
  title,
}: {
  children: ReactNode;
  helperText: string;
  title: string;
}) {
  return (
    <section className="min-w-0 overflow-hidden rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_1px_2px_rgba(9,30,66,0.06),0_12px_32px_rgba(9,30,66,0.05)]">
      <div className="border-b border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-6 py-4">
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
          {title}
        </p>
        <p className="text-anywhere mt-2 text-sm leading-6 text-[#44546f]">
          {helperText}
        </p>
      </div>
      <div className="min-w-0 px-6 py-6 sm:px-8 sm:py-8">{children}</div>
    </section>
  );
}

export default function TaskForm({
  activePane = "document",
  task,
  attachments = [],
  attachmentsUploading = false,
  availableTags,
  canSuggestTags = false,
  canCommitChanges = false,
  committing = false,
  onSubmit,
  onCommit,
  onSuggestTags,
  onDeleteAttachment,
  onOpenAttachment,
  onUploadAttachment,
  disabled = false,
  embeddingsStale = false,
  loading = false,
  suggestingTags = false,
}: Props) {
  const initialSections = useMemo(
    () => parseTaskDocument(task.content),
    [task.content],
  );
  const initialDocumentBody = useMemo(
    () => serializeTaskBodyForEditor(initialSections),
    [initialSections],
  );
  const documentTextareaRef = useRef<HTMLTextAreaElement | null>(null);

  const [title, setTitle] = useState(task.title);
  const [documentBody, setDocumentBody] = useState(initialDocumentBody);
  const [documentMode, setDocumentMode] = useState<"edit" | "preview">("edit");
  const [changeHistory, setChangeHistory] = useState(
    initialSections.changeHistory,
  );
  const [tags, setTags] = useState(task.tags);
  const [tagSuggestions, setTagSuggestions] = useState<
    TaskTagSuggestionResponse["suggestions"]
  >([]);
  const [tagSuggestionsGeneratedAt, setTagSuggestionsGeneratedAt] = useState<
    string | null
  >(null);
  const [tagSuggestionsRequested, setTagSuggestionsRequested] = useState(false);

  useEffect(() => {
    setTitle(task.title);
    setDocumentBody(initialDocumentBody);
    setDocumentMode("edit");
    setChangeHistory(initialSections.changeHistory);
    setTags(task.tags);
    setTagSuggestions([]);
    setTagSuggestionsGeneratedAt(null);
    setTagSuggestionsRequested(false);
  }, [
    initialDocumentBody,
    initialSections.changeHistory,
    task.tags,
    task.title,
  ]);

  const contentChanged =
    normalizeTaskEditorValue(documentBody) !==
      normalizeTaskEditorValue(initialDocumentBody) ||
    normalizeTaskEditorValue(changeHistory) !==
      normalizeTaskEditorValue(initialSections.changeHistory);
  const currentTaskContent = contentChanged
    ? buildTaskDocumentFromEditors(documentBody, changeHistory)
    : task.content;
  const hasUnsavedChanges =
    title !== task.title || contentChanged || !haveSameTags(tags, task.tags);
  const isPostApprovalFlow = [
    "ready_for_dev",
    "in_progress",
    "ready_for_testing",
    "testing",
    "done",
  ].includes(task.status);
  const isAwaitingApproval = task.status === "awaiting_approval";
  const saveDisabled = disabled || loading || !hasUnsavedChanges;
  const commitDisabled =
    !canCommitChanges || committing || hasUnsavedChanges || !embeddingsStale;

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await onSubmit({
      title,
      content: currentTaskContent,
      tags,
    });
  }

  async function handleSuggestTags() {
    if (!onSuggestTags) {
      return;
    }
    try {
      const result = await onSuggestTags({
        title,
        content: currentTaskContent,
        current_tags: tags,
      });
      setTagSuggestions(result.suggestions);
      setTagSuggestionsGeneratedAt(result.generated_at);
      setTagSuggestionsRequested(true);
    } catch {
      setTagSuggestions([]);
      setTagSuggestionsGeneratedAt(null);
      setTagSuggestionsRequested(false);
    }
  }

  function addSuggestedTag(tagName: string) {
    if (tags.includes(tagName)) {
      return;
    }
    setTags([...tags, tagName]);
  }

  function replaceWithSuggestedTags() {
    setTags(tagSuggestions.map((item) => item.tag));
  }

  function insertMarkdownTable() {
    const textarea = documentTextareaRef.current;
    const selectionStart = textarea?.selectionStart ?? documentBody.length;
    const selectionEnd = textarea?.selectionEnd ?? documentBody.length;
    const beforeSelection = documentBody.slice(0, selectionStart);
    const afterSelection = documentBody.slice(selectionEnd);
    const prefix =
      beforeSelection && !beforeSelection.endsWith("\n")
        ? "\n\n"
        : beforeSelection.endsWith("\n\n") || !beforeSelection
          ? ""
          : "\n";
    const suffix =
      afterSelection && !afterSelection.startsWith("\n") ? "\n\n" : "";
    const insertedText = `${prefix}${MARKDOWN_TABLE_TEMPLATE}${suffix}`;
    const nextValue = `${beforeSelection}${insertedText}${afterSelection}`;
    const nextCursor = beforeSelection.length + insertedText.length;

    setDocumentBody(nextValue);
    setDocumentMode("edit");

    window.requestAnimationFrame(() => {
      documentTextareaRef.current?.focus();
      documentTextareaRef.current?.setSelectionRange(nextCursor, nextCursor);
    });
  }

  return (
    <form className="min-w-0 space-y-5" onSubmit={handleSubmit}>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.8fr)_320px] xl:items-start">
        <section className="space-y-5">
          <EditorCard
            helperText=""
            title={
              activePane === "history" ? "История изменений" : "Документ задачи"
            }
          >
            {activePane === "document" ? (
              <div className="space-y-6">
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                    Название задачи
                  </span>
                  <input
                    className="w-full border-0 border-b border-[rgba(9,30,66,0.14)] bg-transparent px-0 py-2 text-[2rem] font-semibold leading-tight text-[#172b4d] outline-none transition-colors placeholder:text-[#97a0af] focus:border-[#0c66e4] focus:ring-0"
                    disabled={disabled}
                    name="task-title"
                    onChange={(event) => setTitle(event.target.value)}
                    placeholder="Название требования"
                    value={title}
                  />
                </label>

                <div className="grid gap-4 sm:grid-cols-3">
                  <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                      Статус
                    </p>
                    <p className="mt-2 text-sm font-medium text-[#172b4d]">
                      {getTaskStatusLabel(task.status)}
                    </p>
                  </div>
                  <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                      Последнее обновление
                    </p>
                    <p className="mt-2 text-sm font-medium text-[#172b4d]">
                      {formatDateTime(task.updated_at)}
                    </p>
                  </div>
                  <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                      Семантический индекс
                    </p>
                    <p className="mt-2 text-sm font-medium text-[#172b4d]">
                      {task.indexed_at
                        ? formatDateTime(task.indexed_at)
                        : "Еще не построен"}
                    </p>
                  </div>
                </div>

                <div>
                  <div className="mb-3 flex min-w-0 flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                    <span className="block text-sm font-semibold text-[#172b4d]">
                      Текст задачи
                    </span>
                    <div className="flex min-w-0 flex-wrap gap-2">
                      <button
                        aria-pressed={documentMode === "edit"}
                        className={
                          documentMode === "edit"
                            ? "ui-button-primary px-3 py-2"
                            : "ui-button-secondary px-3 py-2"
                        }
                        onClick={() => setDocumentMode("edit")}
                        type="button"
                      >
                        Редактирование
                      </button>
                      <button
                        aria-pressed={documentMode === "preview"}
                        className={
                          documentMode === "preview"
                            ? "ui-button-primary px-3 py-2"
                            : "ui-button-secondary px-3 py-2"
                        }
                        onClick={() => setDocumentMode("preview")}
                        type="button"
                      >
                        Предпросмотр
                      </button>
                      <button
                        className="ui-button-secondary px-3 py-2"
                        disabled={disabled}
                        onClick={insertMarkdownTable}
                        type="button"
                      >
                        Вставить таблицу
                      </button>
                    </div>
                  </div>

                  {documentMode === "edit" ? (
                    <label className="block">
                      <span className="sr-only">Текст задачи</span>
                      <textarea
                        className="min-h-[34rem] w-full resize-y rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-4 font-mono text-[14px] leading-7 text-[#172b4d] outline-none transition-colors placeholder:text-[#97a0af] focus:border-[#0c66e4] focus:ring-4 focus:ring-[#dbeafe]"
                        disabled={disabled}
                        name="task-document"
                        onChange={(event) =>
                          setDocumentBody(event.target.value)
                        }
                        placeholder="Опишите задачу как единый документ. При желании используйте заголовки, списки и Markdown-таблицы."
                        ref={documentTextareaRef}
                        value={documentBody}
                      />
                    </label>
                  ) : (
                    <TaskMarkdownPreview markdown={documentBody} />
                  )}
                </div>

                {onUploadAttachment ? (
                  <AttachmentUpload
                    attachments={attachments}
                    busy={attachmentsUploading}
                    disabled={disabled}
                    onDelete={onDeleteAttachment}
                    onOpenAttachment={onOpenAttachment}
                    onUpload={onUploadAttachment}
                  />
                ) : null}
              </div>
            ) : (
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
                  История изменений
                </span>
                <textarea
                  className="min-h-[32rem] w-full resize-y rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-4 text-[15px] leading-8 text-[#172b4d] outline-none transition-colors placeholder:text-[#97a0af] focus:border-[#0c66e4] focus:ring-4 focus:ring-[#dbeafe]"
                  disabled={disabled}
                  name="task-history"
                  onChange={(event) => setChangeHistory(event.target.value)}
                  placeholder="Например: 19.04 — уточнили сценарий авторизации и ограничения по ролям."
                  value={changeHistory}
                />
              </label>
            )}
          </EditorCard>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-6">
          <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Публикация
            </p>
            <p className="mt-3 text-sm leading-7 text-[#44546f]">
              Сохранение обновляет карточку задачи. Commit публикует
              индексированную версию для поиска, проверки и связанных сценариев
              работы с задачей.
            </p>
          </section>

          {activePane === "document" ? (
            <>
              <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
                <TagMultiSelect
                  disabled={disabled}
                  helperText={
                    availableTags.length === 0
                      ? "Администратор еще не добавил теги в справочник."
                      : ""
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
              </section>

              {canSuggestTags ? (
                <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
                  <div className="flex flex-col gap-4">
                    <div className="min-w-0">
                      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                        Подбор тегов
                      </p>
                      <p className="mt-3 text-sm leading-7 text-[#44546f]">
                        Подбирает до 5 тегов из справочника проекта по текущей
                        версии задачи.
                      </p>
                    </div>
                    <button
                      className="ui-button-secondary w-full whitespace-nowrap px-3"
                      disabled={
                        disabled || suggestingTags || availableTags.length === 0
                      }
                      onClick={() => void handleSuggestTags()}
                      type="button"
                    >
                      {suggestingTags ? "Подбираем..." : "Подобрать теги"}
                    </button>
                  </div>

                  {tagSuggestions.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="text-sm font-semibold text-[#172b4d]">
                          Рекомендации
                        </p>
                        <button
                          className="text-sm font-semibold text-[#0c66e4] disabled:text-[#97a0af]"
                          disabled={disabled}
                          onClick={replaceWithSuggestedTags}
                          type="button"
                        >
                          Заменить выбранные
                        </button>
                      </div>
                      <div className="space-y-3">
                        {tagSuggestions.map((item) => {
                          const alreadySelected = tags.includes(item.tag);
                          return (
                            <article
                              key={item.tag}
                              className="min-w-0 rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3"
                            >
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="text-anywhere max-w-full rounded-full bg-white px-3 py-1 text-xs font-semibold text-[#172b4d]">
                                      {item.tag}
                                    </span>
                                    <span className="text-xs font-medium text-[#5e6c84]">
                                      {Math.round(item.confidence * 100)}%
                                    </span>
                                  </div>
                                  <p className="mt-2 text-sm leading-6 text-[#44546f]">
                                    {item.reason}
                                  </p>
                                </div>
                                <button
                                  className="ui-button-secondary"
                                  disabled={disabled || alreadySelected}
                                  onClick={() => addSuggestedTag(item.tag)}
                                  type="button"
                                >
                                  {alreadySelected ? "Уже выбран" : "Добавить"}
                                </button>
                              </div>
                            </article>
                          );
                        })}
                      </div>
                      {tagSuggestionsGeneratedAt ? (
                        <p className="text-xs text-[#626f86]">
                          Сформировано{" "}
                          {formatDateTime(tagSuggestionsGeneratedAt)}
                        </p>
                      ) : null}
                    </div>
                  ) : tagSuggestionsRequested ? (
                    <p className="mt-4 text-sm leading-6 text-[#626f86]">
                      Подходящих тегов с уверенностью 80% и выше не найдено.
                    </p>
                  ) : null}
                </section>
              ) : null}
            </>
          ) : (
            <section className="rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white p-5 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                Как вести историю
              </p>
              <ul className="mt-3 space-y-3 text-sm leading-6 text-[#44546f]">
                <li>
                  Фиксируйте только смысловые изменения, а не каждую мелкую
                  правку.
                </li>
                <li>
                  Указывайте причину изменения, если она важна для команды.
                </li>
                <li>
                  После сохранения при необходимости публикуйте новую версию
                  через commit.
                </li>
              </ul>
            </section>
          )}
        </aside>
      </div>

      <div className="sticky bottom-3 z-10 flex min-w-0 flex-col gap-4 rounded-[16px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-4 shadow-[0_12px_24px_rgba(9,30,66,0.08)] sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0 space-y-1">
          <p className="text-anywhere text-sm font-medium text-[#172b4d]">
            {hasUnsavedChanges
              ? "Есть несохраненные изменения."
              : embeddingsStale && canCommitChanges
                ? "Изменения сохранены. Выполните commit, чтобы обновить семантическую версию задачи."
                : isPostApprovalFlow
                  ? "Документ синхронизирован. Новые правки можно публиковать отдельным commit."
                  : "Страница синхронизирована с текущей карточкой задачи."}
          </p>
        </div>

        <div className="flex min-w-0 flex-wrap gap-3">
          {canCommitChanges ? (
            <button
              className="ui-button-secondary"
              disabled={commitDisabled}
              onClick={() => void onCommit?.()}
              type="button"
            >
              {committing ? "Публикуем commit..." : "Commit изменений"}
            </button>
          ) : null}
          <button
            className="ui-button-primary min-w-[10rem]"
            disabled={saveDisabled}
            type="submit"
          >
            {loading ? "Сохраняем..." : "Сохранить страницу"}
          </button>
        </div>
      </div>
    </form>
  );
}
