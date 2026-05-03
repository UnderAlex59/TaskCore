import { Link } from "react-router-dom";

import type { TaskRead } from "@/api/tasksApi";
import {
  formatShortDate,
  getTaskStatusLabel,
  getValidationVerdictLabel,
} from "@/shared/lib/locale";

interface Props {
  detailHref?: string;
  task: TaskRead;
}

function getPreview(content: string) {
  return content.replaceAll(/\s+/g, " ").trim().slice(0, 220);
}

function getStatusClassName(status: TaskRead["status"]) {
  if (status === "done") {
    return "border-[rgba(34,154,22,0.2)] bg-[#e8f5e9] text-[#216e1f]";
  }

  if (status === "needs_rework" || status === "awaiting_approval") {
    return "border-[rgba(172,107,8,0.2)] bg-[#fff4e5] text-[#7f4c00]";
  }

  if (status === "validating" || status === "testing") {
    return "border-[rgba(98,111,134,0.22)] bg-[#f7f8fa] text-[#44546f]";
  }

  return "border-[rgba(12,102,228,0.18)] bg-[#e9f2ff] text-[#0c66e4]";
}

export default function TaskCard({ detailHref, task }: Props) {
  const verdict = task.validation_result?.verdict;

  return (
    <article className="work-card px-5 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span
          className={["status-pill", getStatusClassName(task.status)].join(" ")}
        >
          {getTaskStatusLabel(task.status)}
        </span>
        {verdict ? (
          <span className="status-pill border-[rgba(9,30,66,0.08)] bg-[#f7f8fa] text-[#44546f]">
            Проверка: {getValidationVerdictLabel(verdict)}
          </span>
        ) : null}
      </div>

      <h3 className="text-anywhere mt-4 text-xl font-semibold text-[#172b4d]">
        {task.title}
      </h3>
      <p className="text-anywhere mt-3 text-sm leading-7 text-[#44546f]">
        {getPreview(task.content) || "Текст задачи пока не заполнен."}
      </p>

      {task.tags.length > 0 ? (
        <div className="mt-4 flex min-w-0 flex-wrap gap-2">
          {task.tags.map((tag) => (
            <span
              key={tag}
              className="text-anywhere max-w-full rounded-full border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-3 py-1 text-xs font-semibold text-[#44546f]"
            >
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-5 flex flex-col gap-4 border-t border-[rgba(9,30,66,0.08)] pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-x-5 gap-y-2 text-xs text-[#626f86]">
          <span>Создана {formatShortDate(task.created_at)}</span>
          <span>Обновлена {formatShortDate(task.updated_at)}</span>
          {task.attachments.length > 0 ? (
            <span>Вложения: {task.attachments.length}</span>
          ) : null}
        </div>
        {detailHref ? (
          <Link className="ui-button-secondary shrink-0" to={detailHref}>
            Открыть задачу
          </Link>
        ) : null}
      </div>
    </article>
  );
}
