import { useEffect, useId, useState, type ChangeEvent } from "react";

import type { TaskAttachmentRead } from "@/api/tasksApi";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";

interface Props {
  attachments: TaskAttachmentRead[];
  busy?: boolean;
  disabled?: boolean;
  onDelete?: (attachment: TaskAttachmentRead) => Promise<void>;
  onOpenAttachment?: (attachment: TaskAttachmentRead) => Promise<Blob>;
  onUpload: (file: File) => Promise<void>;
}

type PreviewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; objectUrl?: string; text?: string }
  | { status: "error"; message: string };

function isImageAttachment(attachment: TaskAttachmentRead) {
  return attachment.content_type.startsWith("image/");
}

function isPdfAttachment(attachment: TaskAttachmentRead) {
  return attachment.content_type === "application/pdf";
}

function isTextAttachment(attachment: TaskAttachmentRead) {
  return (
    attachment.content_type.startsWith("text/") ||
    attachment.content_type === "application/json" ||
    attachment.content_type === "application/xml"
  );
}

export default function AttachmentUpload({
  attachments,
  onUpload,
  onOpenAttachment,
  onDelete,
  disabled = false,
  busy = false,
}: Props) {
  const modalTitleId = useId();
  const [selectedAttachment, setSelectedAttachment] =
    useState<TaskAttachmentRead | null>(null);
  const [preview, setPreview] = useState<PreviewState>({ status: "idle" });
  const [deleteTarget, setDeleteTarget] = useState<TaskAttachmentRead | null>(
    null,
  );
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    await onUpload(file);
    event.target.value = "";
  }

  useEffect(() => {
    if (!selectedAttachment || !onOpenAttachment) {
      setPreview({ status: "idle" });
      return undefined;
    }

    let active = true;
    let objectUrl: string | undefined;
    setPreview({ status: "loading" });

    void onOpenAttachment(selectedAttachment)
      .then(async (blob) => {
        if (!active) {
          return;
        }

        if (isTextAttachment(selectedAttachment)) {
          const text = await blob.text();
          if (active) {
            setPreview({ status: "ready", text });
          }
          return;
        }

        objectUrl = URL.createObjectURL(blob);
        setPreview({ status: "ready", objectUrl });
      })
      .catch(() => {
        if (active) {
          setPreview({
            status: "error",
            message: "Не удалось открыть вложение.",
          });
        }
      });

    return () => {
      active = false;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [onOpenAttachment, selectedAttachment]);

  useEffect(() => {
    if (!selectedAttachment) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        setSelectedAttachment(null);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [selectedAttachment]);

  async function confirmDelete() {
    if (!deleteTarget || !onDelete) {
      return;
    }

    setDeletingId(deleteTarget.id);
    try {
      await onDelete(deleteTarget);
      if (selectedAttachment?.id === deleteTarget.id) {
        setSelectedAttachment(null);
      }
      setDeleteTarget(null);
    } catch {
      // Ошибка показывается на уровне страницы через общий error state.
    } finally {
      setDeletingId(null);
    }
  }

  function renderPreview() {
    if (!selectedAttachment) {
      return null;
    }

    if (preview.status === "loading") {
      return (
        <div className="flex min-h-[18rem] items-center justify-center rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] text-sm text-[#626f86]">
          Открываем файл...
        </div>
      );
    }

    if (preview.status === "error") {
      return (
        <div className="rounded-[12px] border border-[rgba(174,46,36,0.16)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]">
          {preview.message}
        </div>
      );
    }

    if (preview.status !== "ready") {
      return null;
    }

    if (preview.text !== undefined) {
      return (
        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] p-4 text-sm leading-6 text-[#172b4d]">
          {preview.text || "Файл пуст."}
        </pre>
      );
    }

    if (preview.objectUrl && isImageAttachment(selectedAttachment)) {
      return (
        <div className="flex max-h-[62vh] items-center justify-center overflow-auto rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#f7f8fa] p-3">
          <img
            alt={selectedAttachment.alt_text ?? selectedAttachment.filename}
            className="max-h-[58vh] max-w-full object-contain"
            src={preview.objectUrl}
          />
        </div>
      );
    }

    if (preview.objectUrl && isPdfAttachment(selectedAttachment)) {
      return (
        <iframe
          className="h-[62vh] w-full rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-white"
          src={preview.objectUrl}
          title={selectedAttachment.filename}
        />
      );
    }

    return (
      <div className="rounded-[12px] border border-[rgba(9,30,66,0.1)] bg-[#fafbfc] px-4 py-4 text-sm leading-6 text-[#44546f]">
        Для этого типа файла предпросмотр недоступен.
        {preview.objectUrl ? (
          <a
            className="ml-2 font-semibold text-[#0c66e4] hover:text-[#0055cc]"
            download={selectedAttachment.filename}
            href={preview.objectUrl}
          >
            Скачать файл
          </a>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rounded-[16px] border border-dashed border-[rgba(9,30,66,0.12)] bg-[#fafbfc] p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-[#172b4d]">
            Прикрепленные материалы
          </p>
          <p className="mt-1 text-sm leading-6 text-[#626f86]">
            Загрузите файлы, макеты, исследования или спецификации, которые
            должны участвовать в обсуждении и индексации задачи.
          </p>
        </div>
        <label className="ui-button-secondary cursor-pointer whitespace-nowrap">
          <span>{busy ? "Загружаем..." : "Загрузить файл"}</span>
          <input
            className="hidden"
            disabled={disabled || busy}
            onChange={handleChange}
            type="file"
          />
        </label>
      </div>

      <div className="mt-4 space-y-3">
        {attachments.length === 0 ? (
          <div className="rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-white px-4 py-4 text-sm leading-6 text-[#626f86]">
            Файлы пока не загружены.
          </div>
        ) : (
          attachments.map((attachment) => (
            <article
              key={attachment.id}
              className="rounded-[14px] border border-[rgba(9,30,66,0.1)] bg-white px-4 py-4"
            >
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <p className="text-anywhere font-medium text-[#172b4d]">
                    {attachment.filename}
                  </p>
                  <p className="mt-1 text-sm leading-6 text-[#44546f]">
                    {attachment.content_type}
                  </p>
                  {attachment.alt_text ? (
                    <p className="text-anywhere mt-2 rounded-[12px] bg-[#f7f8fa] px-3 py-2 text-sm leading-6 text-[#172b4d]">
                      <span className="font-semibold">Alt-text: </span>
                      {attachment.alt_text}
                    </p>
                  ) : (
                    <p className="mt-2 text-sm leading-6 text-[#626f86]">
                      Alt-text не определен.
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 flex-wrap gap-2">
                  {onOpenAttachment ? (
                    <button
                      className="ui-button-secondary px-3 py-2 text-xs"
                      onClick={() => setSelectedAttachment(attachment)}
                      type="button"
                    >
                      Просмотреть
                    </button>
                  ) : null}
                  {onDelete ? (
                    <button
                      className="ui-button-danger px-3 py-2 text-xs"
                      disabled={disabled || deletingId === attachment.id}
                      onClick={() => setDeleteTarget(attachment)}
                      type="button"
                    >
                      {deletingId === attachment.id ? "Удаляем..." : "Удалить"}
                    </button>
                  ) : null}
                </div>
              </div>
            </article>
          ))
        )}
      </div>

      {selectedAttachment ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(9,30,66,0.28)] px-4 py-6 [overscroll-behavior:contain]"
          onClick={() => setSelectedAttachment(null)}
        >
          <div
            aria-labelledby={modalTitleId}
            aria-modal="true"
            className="flex max-h-[92vh] w-full max-w-5xl flex-col rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_24px_56px_rgba(9,30,66,0.2)]"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <header className="flex flex-col gap-3 border-b border-[rgba(9,30,66,0.08)] px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
              <div className="min-w-0">
                <h2
                  className="text-anywhere text-lg font-semibold text-[#172b4d]"
                  id={modalTitleId}
                >
                  {selectedAttachment.filename}
                </h2>
                <p className="mt-1 text-sm text-[#626f86]">
                  {selectedAttachment.content_type}
                </p>
              </div>
              <div className="flex shrink-0 gap-2">
                {preview.status === "ready" && preview.objectUrl ? (
                  <a
                    className="ui-button-secondary px-3 py-2 text-xs"
                    download={selectedAttachment.filename}
                    href={preview.objectUrl}
                  >
                    Скачать
                  </a>
                ) : null}
                <button
                  className="ui-button-secondary px-3 py-2 text-xs"
                  onClick={() => setSelectedAttachment(null)}
                  type="button"
                >
                  Закрыть
                </button>
              </div>
            </header>
            <div className="min-h-0 overflow-auto px-5 py-5">
              {selectedAttachment.alt_text ? (
                <section className="mb-4 rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
                    Alt-text
                  </p>
                  <p className="text-anywhere mt-2 text-sm leading-6 text-[#172b4d]">
                    {selectedAttachment.alt_text}
                  </p>
                </section>
              ) : null}
              {renderPreview()}
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        busy={deletingId !== null}
        cancelLabel="Отмена"
        confirmLabel="Удалить"
        description={
          deleteTarget
            ? `Вложение "${deleteTarget.filename}" будет удалено из задачи и больше не будет участвовать в индексации.`
            : ""
        }
        destructive
        onClose={() => {
          if (deletingId === null) {
            setDeleteTarget(null);
          }
        }}
        onConfirm={confirmDelete}
        open={deleteTarget !== null}
        title="Удалить вложение"
      />
    </div>
  );
}
