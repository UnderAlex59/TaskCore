import { Link } from "react-router-dom";

import type { ProjectRead } from "@/api/projectsApi";
import { formatShortDate } from "@/shared/lib/locale";

interface Props {
  canDelete?: boolean;
  canManageRules?: boolean;
  onDelete?: (projectId: string) => void | Promise<void>;
  project: ProjectRead;
}

function formatDate(value: string) {
  return formatShortDate(value);
}

export default function ProjectCard({
  project,
  onDelete,
  canDelete = false,
  canManageRules = false,
}: Props) {
  return (
    <article className="glass-panel border border-black/10 p-6 shadow-panel">
      <p className="section-eyebrow">Проект</p>
      <h3 className="mt-3 text-balance text-2xl font-bold text-ink">
        {project.name}
      </h3>
      <p className="mt-3 break-words text-sm leading-7 text-slate/80">
        {project.description ?? "Описание проекта пока не заполнено."}
      </p>
      <div className="mt-5 text-xs font-medium uppercase tracking-[0.14em] text-slate/60">
        Обновлён {formatDate(project.updated_at)}
      </div>
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Link
          className="ui-button-primary"
          to={`/projects/${project.id}/tasks`}
        >
          Открыть задачи
        </Link>
        {canManageRules ? (
          <Link
            className="ui-button-secondary"
            to={`/admin/projects/${project.id}/rules`}
          >
            Правила и узлы
          </Link>
        ) : null}
        {canDelete && onDelete ? (
          <button
            className="ui-button-danger"
            onClick={() => void onDelete(project.id)}
            type="button"
          >
            Удалить
          </button>
        ) : null}
      </div>
    </article>
  );
}
