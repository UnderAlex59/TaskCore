import { useEffect, useState } from "react";

import {
  projectsApi,
  type ProjectCreate,
  type ProjectRead,
} from "@/api/projectsApi";
import CreateProjectModal from "@/features/projects/CreateProjectModal";
import ProjectCard from "@/features/projects/ProjectCard";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getRoleLabel } from "@/shared/lib/locale";
import { useAuthStore } from "@/store/authStore";

const PROJECT_CREATORS = new Set(["ADMIN", "ANALYST", "MANAGER"]);

export default function ProjectList() {
  const user = useAuthStore((state) => state.user);
  const [projects, setProjects] = useState<ProjectRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [projectPendingDeletion, setProjectPendingDeletion] =
    useState<ProjectRead | null>(null);

  async function loadProjects() {
    try {
      setLoading(true);
      setError(null);
      setProjects(await projectsApi.list());
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось загрузить проекты."));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadProjects();
  }, []);

  async function handleCreate(payload: ProjectCreate) {
    try {
      setCreating(true);
      const created = await projectsApi.create(payload);
      setProjects((current) => [created, ...current]);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось создать проект."));
    } finally {
      setCreating(false);
    }
  }

  function requestDelete(projectId: string) {
    const project = projects.find((item) => item.id === projectId);
    if (!project) {
      return;
    }
    setProjectPendingDeletion(project);
  }

  async function handleDelete() {
    if (!projectPendingDeletion) {
      return;
    }

    try {
      setDeletingProjectId(projectPendingDeletion.id);
      await projectsApi.remove(projectPendingDeletion.id);
      setProjects((current) =>
        current.filter((project) => project.id !== projectPendingDeletion.id),
      );
      setProjectPendingDeletion(null);
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось удалить проект."));
    } finally {
      setDeletingProjectId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка проектов" />;
  }

  const canCreateProject = PROJECT_CREATORS.has(user?.role ?? "");

  return (
    <section className="space-y-6">
      <header className="page-panel px-5 py-5 sm:px-7 sm:py-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 max-w-3xl">
            <p className="section-eyebrow">Проекты</p>
            <h2 className="text-anywhere mt-3 text-3xl font-semibold text-[#172b4d] sm:text-4xl">
              Проекты рабочего пространства
            </h2>
            <p className="mt-4 text-sm leading-7 text-[#44546f]">
              Создавайте проекты, распределяйте команду и ведите постановки
              задач в едином рабочем контуре.
            </p>
          </div>
          <CreateProjectModal
            canCreate={canCreateProject}
            loading={creating}
            onCreate={handleCreate}
          />
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-3">
          <div className="metric-tile">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Проектов
            </p>
            <p className="mt-2 text-2xl font-semibold text-[#172b4d]">
              {projects.length}
            </p>
          </div>
          <div className="metric-tile">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Роль
            </p>
            <p className="mt-2 text-sm font-semibold text-[#172b4d]">
              {user?.role ? getRoleLabel(user.role) : "Не указана"}
            </p>
          </div>
          <div className="metric-tile">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#5e6c84]">
              Создание
            </p>
            <p className="mt-2 text-sm font-semibold text-[#172b4d]">
              {canCreateProject ? "Доступно" : "Только просмотр"}
            </p>
          </div>
        </div>

        {error ? (
          <p
            aria-live="polite"
            className="mt-4 rounded-[12px] border border-[rgba(174,46,36,0.18)] bg-[#fdecec] px-4 py-3 text-sm text-[#ae2e24]"
          >
            {error}
          </p>
        ) : null}
      </header>

      {projects.length === 0 ? (
        <div className="page-panel border-dashed px-6 py-8">
          <p className="text-lg font-semibold text-[#172b4d]">
            Проектов пока нет
          </p>
          <p className="mt-2 max-w-2xl text-sm leading-7 text-[#626f86]">
            Создайте первый проект, чтобы начать работу с задачами, участниками
            и правилами проверки.
          </p>
        </div>
      ) : (
        <div className="grid min-w-0 gap-5 xl:grid-cols-2">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              canDelete={user?.role === "ADMIN"}
              canManageRules={user?.role === "ADMIN"}
              onDelete={requestDelete}
              project={project}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        busy={deletingProjectId === projectPendingDeletion?.id}
        confirmLabel="Удалить проект"
        description={
          projectPendingDeletion
            ? `Удалить проект «${projectPendingDeletion.name}»? Вместе с ним исчезнут его связи и рабочий контекст.`
            : ""
        }
        destructive
        onClose={() => setProjectPendingDeletion(null)}
        onConfirm={handleDelete}
        open={projectPendingDeletion !== null}
        title="Удаление проекта"
      />
    </section>
  );
}
