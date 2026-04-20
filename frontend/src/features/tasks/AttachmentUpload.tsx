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
              <p className="font-medium text-[#172b4d]">
                {attachment.filename}
              </p>
              <p className="mt-1 text-sm leading-6 text-[#44546f]">
                {attachment.alt_text ?? attachment.content_type}
              </p>
            </article>
          ))
        )}
      </div>
    </div>
  );
}
