import { useEffect, useState } from "react";

import CreateProjectModal from "@/features/projects/CreateProjectModal";
import ProjectCard from "@/features/projects/ProjectCard";
import {
  projectsApi,
  type ProjectCreate,
  type ProjectRead,
} from "@/api/projectsApi";
import { useAuthStore } from "@/store/authStore";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";

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
      <header className="glass-panel border border-black/10 p-6 shadow-panel sm:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="section-eyebrow">Проекты</p>
            <h2 className="mt-3 text-3xl font-bold text-ink sm:text-4xl">
              Проекты рабочего пространства
            </h2>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate/80">
              Первый зарегистрированный пользователь становится администратором
              платформы. Аналитики, менеджеры и администраторы могут создавать
              проекты; создатель проекта автоматически получает роль менеджера
              внутри него.
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
            className="mt-4 rounded-[10px] bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {error}
          </p>
        ) : null}
      </header>

      {projects.length === 0 ? (
        <div className="glass-panel border border-dashed border-black/10 p-8 text-sm text-slate/70 shadow-panel">
          Проектов пока нет. Создайте первый проект, чтобы начать добавлять
          участников и задачи.
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
