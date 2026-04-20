import { Link } from "react-router-dom";

import type { ProjectRead } from "@/api/projectsApi";
import { formatShortDate } from "@/shared/lib/locale";

interface Props {
  canDelete?: boolean;
  canManageRules?: boolean;
  onDelete?: (projectId: string) => void | Promise<void>;
  project: ProjectRead;
}

export default function ProjectCard({
  project,
  onDelete,
  canDelete = false,
  canManageRules = false,
}: Props) {
  return (
    <article className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
            Проект
          </p>
          <h3 className="mt-3 text-2xl font-semibold text-[#172b4d]">
            {project.name}
          </h3>
          <p className="mt-3 break-words text-sm leading-7 text-[#44546f]">
            {project.description ?? "Описание проекта пока не заполнено."}
          </p>
        </div>
        <div className="shrink-0 rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3 text-sm text-[#44546f]">
          Обновлен {formatShortDate(project.updated_at)}
        </div>
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
            Правила проекта
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
