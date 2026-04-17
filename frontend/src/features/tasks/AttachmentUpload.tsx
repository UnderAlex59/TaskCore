import type { TaskAttachmentRead } from "@/api/tasksApi";

interface Props {
  attachments: TaskAttachmentRead[];
  busy?: boolean;
  disabled?: boolean;
  onUpload: (file: File) => Promise<void>;
}

export default function AttachmentUpload({
  attachments,
  onUpload,
  disabled = false,
  busy = false,
}: Props) {
  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    await onUpload(file);
    event.target.value = "";
  }

  return (
    <div className="rounded-[10px] border border-dashed border-black/10 p-5">
      <p className="text-sm font-semibold text-ink">Вложения</p>
      <label className="ui-button-primary mt-3 cursor-pointer">
        <span>{busy ? "Загружаем..." : "Загрузить файл"}</span>
        <input
          className="hidden"
          disabled={disabled || busy}
          onChange={handleChange}
          type="file"
        />
      </label>
      <div className="mt-4 space-y-2">
        {attachments.length === 0 ? (
          <p className="text-sm leading-7 text-slate/70">
            Файлы пока не загружены.
          </p>
        ) : (
          attachments.map((attachment) => (
            <div
              key={attachment.id}
              className="rounded-[8px] bg-white/70 px-3 py-2 text-sm text-slate/80"
            >
              <p className="font-semibold text-ink">{attachment.filename}</p>
              <p>{attachment.alt_text ?? attachment.content_type}</p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
