import type { TaskRead } from "@/api/tasksApi";
import {
  getTaskStatusLabel,
  getValidationVerdictLabel,
} from "@/shared/lib/locale";

interface Props {
  task: TaskRead;
}

function getPreview(content: string) {
  return content.replaceAll(/\s+/g, " ").trim().slice(0, 220);
}

export default function TaskCard({ task }: Props) {
  const verdict = task.validation_result?.verdict;

  return (
    <article className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-[#e9f2ff] px-3 py-1 text-xs font-semibold text-[#0c66e4]">
          {getTaskStatusLabel(task.status)}
        </span>
        {verdict ? (
          <span className="rounded-full bg-[#f7f8fa] px-3 py-1 text-xs font-medium text-[#44546f]">
            Проверка: {getValidationVerdictLabel(verdict)}
          </span>
        ) : null}
      </div>

      <h3 className="mt-4 text-xl font-semibold text-[#172b4d]">
        {task.title}
      </h3>
      <p className="mt-3 break-words text-sm leading-7 text-[#44546f]">
        {getPreview(task.content) || "Текст задачи пока не заполнен."}
      </p>

      {task.tags.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {task.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-3 py-1 text-xs font-semibold text-[#44546f]"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : null}
    </article>
  );
}
