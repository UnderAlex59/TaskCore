import type { TaskRead } from "@/api/tasksApi";
import {
  getTaskStatusLabel,
  getValidationVerdictLabel,
} from "@/shared/lib/locale";

interface Props {
  task: TaskRead;
}

export default function TaskCard({ task }: Props) {
  const verdict = task.validation_result?.verdict;

  return (
    <article className="glass-panel border border-black/10 p-5 shadow-panel">
      <p className="text-xs font-bold uppercase tracking-[0.16em] text-ember">
        {getTaskStatusLabel(task.status)}
      </p>
      <h3 className="mt-2 text-balance text-xl font-bold text-ink">
        {task.title}
      </h3>
      <p className="mt-3 break-words text-sm leading-7 text-slate/80">
        {task.content}
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        {task.tags.map((tag) => (
          <span
            key={tag}
            className="rounded-[8px] bg-black/5 px-3 py-1 text-xs font-semibold text-slate/80"
          >
            {tag}
          </span>
        ))}
      </div>
      {verdict ? (
        <p className="mt-4 text-xs font-semibold uppercase tracking-[0.16em] text-pine">
          Проверка: {getValidationVerdictLabel(verdict)}
        </p>
      ) : null}
    </article>
  );
}
