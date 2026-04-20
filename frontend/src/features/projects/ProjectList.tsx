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

  return (
    <section className="space-y-6">
      <header className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-6 sm:px-8">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="max-w-3xl">
            <p className="section-eyebrow">Projects</p>
            <h2 className="mt-3 text-3xl font-semibold text-[#172b4d] sm:text-4xl">
              Проекты рабочего пространства
            </h2>
            <p className="mt-4 text-sm leading-7 text-[#44546f]">
              Создавайте проекты, распределяйте команду и ведите постановки
              задач в едином рабочем контуре.
            </p>
          </div>
          <CreateProjectModal
            canCreate={PROJECT_CREATORS.has(user?.role ?? "")}
            loading={creating}
            onCreate={handleCreate}
          />
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
        <div className="rounded-[18px] border border-dashed border-[rgba(9,30,66,0.12)] bg-white px-6 py-8 text-sm leading-7 text-[#626f86]">
          Проектов пока нет. Создайте первый проект, чтобы начать работу с
          задачами и участниками.
        </div>
      ) : (
        <div className="grid gap-5 xl:grid-cols-2">
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
