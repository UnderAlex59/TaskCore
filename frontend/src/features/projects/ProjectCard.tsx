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
    <article className="work-card overflow-hidden">
      <div className="h-1 bg-[#0c66e4]" />
      <div className="px-5 py-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
              Проект
            </p>
            <h3 className="text-anywhere mt-2 text-2xl font-semibold leading-tight text-[#172b4d]">
              {project.name}
            </h3>
            <p className="text-anywhere mt-3 text-sm leading-7 text-[#44546f]">
              {project.description ?? "Описание проекта пока не заполнено."}
            </p>
          </div>
          <div className="text-anywhere max-w-full shrink-0 rounded-[12px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-3 py-2 text-xs font-medium text-[#44546f] sm:max-w-[16rem]">
            Обновлен {formatShortDate(project.updated_at)}
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-3 border-t border-[rgba(9,30,66,0.08)] pt-4">
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
      </div>
    </article>
  );
}
