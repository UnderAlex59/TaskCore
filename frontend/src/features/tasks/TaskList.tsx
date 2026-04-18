import {
  startTransition,
  useDeferredValue,
  useEffect,
  useEffectEvent,
  useState,
} from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import type { UserRole } from "@/api/authApi";
import {
  projectsApi,
  type ProjectMemberRead,
  type ProjectRead,
} from "@/api/projectsApi";
import {
  tasksApi,
  type TaskCreate,
  type TaskRead,
  type TaskStatus,
} from "@/api/tasksApi";
import { taskTagsApi, type TaskTagOption } from "@/api/taskTagsApi";
import { usersApi, type UserSummary } from "@/api/usersApi";
import TaskCard from "@/features/tasks/TaskCard";
import TagMultiSelect from "@/shared/components/TagMultiSelect";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getRoleLabel } from "@/shared/lib/locale";
import { useAuthStore } from "@/store/authStore";

const TASK_CREATORS = new Set(["ADMIN", "ANALYST"]);
const PROJECT_MEMBER_ROLES: UserRole[] = [
  "MANAGER",
  "ANALYST",
  "DEVELOPER",
  "TESTER",
  "ADMIN",
];
const STATUS_OPTIONS: Array<{ label: string; value: TaskStatus | "" }> = [
  { label: "Все статусы", value: "" },
  { label: "Черновик", value: "draft" },
  { label: "Нужна доработка", value: "needs_rework" },
  { label: "Ожидает подтверждения", value: "awaiting_approval" },
  { label: "Готово к разработке", value: "ready_for_dev" },
  { label: "В работе", value: "in_progress" },
  { label: "Готово", value: "done" },
];

const EMPTY_TASK: TaskCreate = {
  title: "",
  content: "",
  tags: [],
};

export default function TaskList() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);

  const [project, setProject] = useState<ProjectRead | null>(null);
  const [tasks, setTasks] = useState<TaskRead[]>([]);
  const [taskTags, setTaskTags] = useState<TaskTagOption[]>([]);
  const [members, setMembers] = useState<ProjectMemberRead[]>([]);
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creatingTask, setCreatingTask] = useState(false);
  const [savingMember, setSavingMember] = useState(false);
  const [removingMemberId, setRemovingMemberId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "">("");
  const [taskForm, setTaskForm] = useState<TaskCreate>(EMPTY_TASK);
  const [memberUserId, setMemberUserId] = useState("");
  const [memberRole, setMemberRole] = useState<UserRole>("DEVELOPER");
  const [memberPendingRemoval, setMemberPendingRemoval] =
    useState<ProjectMemberRead | null>(null);

  const deferredSearch = useDeferredValue(search);

  async function loadData() {
    if (!projectId) {
      setError("Не найден идентификатор проекта.");
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const shouldLoadUsers = ["ADMIN", "ANALYST", "MANAGER"].includes(
        user?.role ?? "",
      );
      const [
        loadedProject,
        loadedTasks,
        loadedMembers,
        loadedUsers,
        loadedTaskTags,
      ] = await Promise.all([
        projectsApi.get(projectId),
        tasksApi.list(projectId, {
          search: deferredSearch || undefined,
          status: statusFilter || undefined,
          size: 100,
        }),
        projectsApi.listMembers(projectId),
        shouldLoadUsers ? usersApi.list() : Promise.resolve([]),
        taskTagsApi.list(),
      ]);
      setProject(loadedProject);
      setTasks(loadedTasks);
      setTaskTags(loadedTaskTags);
      setMembers(loadedMembers);
      setUsers(loadedUsers);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось загрузить задачи проекта."),
      );
    } finally {
      setLoading(false);
    }
  }

  const onLoadData = useEffectEvent(loadData);

  useEffect(() => {
    void onLoadData();
  }, [projectId, deferredSearch, statusFilter, user?.role]); // eslint-disable-line react-hooks/exhaustive-deps

  const currentMembership = members.find(
    (member) => member.user_id === user?.id,
  );
  const canManageMembers =
    user?.role === "ADMIN" ||
    currentMembership?.role === "MANAGER" ||
    currentMembership?.role === "ADMIN";
  const canCreateTask = TASK_CREATORS.has(user?.role ?? "");
  const availableUsers = users.filter(
    (candidate) => !members.some((member) => member.user_id === candidate.id),
  );

  async function handleCreateTask(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId) {
      return;
    }

    try {
      setCreatingTask(true);
      const created = await tasksApi.create(projectId, {
        ...taskForm,
        tags: taskForm.tags?.filter(Boolean) ?? [],
      });
      setTasks((current) => [created, ...current]);
      setTaskForm(EMPTY_TASK);
      startTransition(() => {
        navigate(`/projects/${projectId}/tasks/${created.id}`);
      });
    } catch (caught) {
      setError(getApiErrorMessage(caught, "Не удалось создать задачу."));
    } finally {
      setCreatingTask(false);
    }
  }

  async function handleAddMember(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || !memberUserId) {
      return;
    }

    try {
      setSavingMember(true);
      const created = await projectsApi.addMember(projectId, {
        user_id: memberUserId,
        role: memberRole,
      });
      setMembers((current) => [...current, created]);
      setMemberUserId("");
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось добавить участника проекта."),
      );
    } finally {
      setSavingMember(false);
    }
  }

  function requestRemoveMember(userId: string) {
    const member = members.find((item) => item.user_id === userId);
    if (!member) {
      return;
    }
    setMemberPendingRemoval(member);
  }

  async function handleRemoveMember() {
    if (!projectId || !memberPendingRemoval) {
      return;
    }

    try {
      setRemovingMemberId(memberPendingRemoval.user_id);
      await projectsApi.removeMember(projectId, memberPendingRemoval.user_id);
      setMembers((current) =>
        current.filter(
          (member) => member.user_id !== memberPendingRemoval.user_id,
        ),
      );
      setMemberPendingRemoval(null);
    } catch (caught) {
      setError(
        getApiErrorMessage(caught, "Не удалось удалить участника проекта."),
      );
    } finally {
      setRemovingMemberId(null);
    }
  }

  if (loading) {
    return <LoadingSpinner label="Загрузка задач" />;
  }

  return (
    <section className="space-y-6">
      <header className="glass-panel border border-black/10 p-5 shadow-panel sm:p-8">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <p className="section-eyebrow">Задачи</p>
            <h2 className="mt-3 text-balance text-3xl font-bold text-ink sm:text-4xl">
              {project?.name ?? "Задачи проекта"}
            </h2>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-slate/80">
              Создавайте требования, отправляйте их на ревью и формируйте
              команду задачи только после успешного подтверждения.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <label className="block">
              <span className="sr-only">Поиск задач</span>
              <input
                autoComplete="off"
                className="ui-field"
                name="task-search"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Поиск по названию или содержанию..."
                type="search"
                value={search}
              />
            </label>
            <label className="block">
              <span className="sr-only">Фильтр по статусу</span>
              <select
                className="ui-field"
                name="task-status-filter"
                onChange={(event) =>
                  setStatusFilter(event.target.value as TaskStatus | "")
                }
                value={statusFilter}
              >
                {STATUS_OPTIONS.map((option) => (
                  <option key={option.label} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
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

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.8fr]">
        <div className="space-y-4">
          {tasks.length === 0 ? (
            <div className="glass-panel border border-dashed border-black/10 p-6 text-sm text-slate/70 shadow-panel">
              По текущим фильтрам задачи не найдены.
            </div>
          ) : (
            tasks.map((task) => (
              <div
                key={task.id}
                className="space-y-3 [content-visibility:auto] [contain-intrinsic-size:220px]"
              >
                <TaskCard task={task} />
                <Link
                  className="ui-button-primary"
                  to={`/projects/${projectId}/tasks/${task.id}`}
                >
                  Открыть задачу
                </Link>
              </div>
            ))
          )}
        </div>

        <div className="space-y-6">
          {canCreateTask ? (
            <form
              className="glass-panel space-y-4 border border-black/10 p-5 shadow-panel sm:p-6"
              onSubmit={handleCreateTask}
            >
              <h3 className="text-xl font-bold text-ink">Новая задача</h3>
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-ink/70">
                  Название задачи
                </span>
                <input
                  autoComplete="off"
                  className="ui-field"
                  name="task-title"
                  onChange={(event) =>
                    setTaskForm((current) => ({
                      ...current,
                      title: event.target.value,
                    }))
                  }
                  placeholder="Уточнить критерии приемки"
                  required
                  value={taskForm.title}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-ink/70">
                  Текст требования
                </span>
                <textarea
                  className="ui-field min-h-36"
                  name="task-content"
                  onChange={(event) =>
                    setTaskForm((current) => ({
                      ...current,
                      content: event.target.value,
                    }))
                  }
                  placeholder="Опишите требование, ограничения и ожидаемый результат..."
                  value={taskForm.content}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-ink/70">
                  Теги
                </span>
                <TagMultiSelect
                  helperText={
                    taskTags.length === 0
                      ? "Администратор ещё не добавил теги в справочник."
                      : "Теги выбираются только из справочника."
                  }
                  hideLabel
                  label="Теги"
                  name="task-tags"
                  noOptionsLabel="Справочник тегов пока пуст"
                  onChange={(tags) =>
                    setTaskForm((current) => ({
                      ...current,
                      tags,
                    }))
                  }
                  options={taskTags}
                  placeholder="Выберите теги"
                  searchPlaceholder="Найти тег"
                  value={taskForm.tags ?? []}
                />
              </label>
              <p className="rounded-[10px] bg-black/5 px-4 py-3 text-sm text-slate/75">
                Команда задачи назначается после успешного ревью: отдельно
                разработчик и тестировщик.
              </p>
              <button
                className="ui-button-primary"
                disabled={creatingTask}
                type="submit"
              >
                {creatingTask ? "Создаем..." : "Создать задачу"}
              </button>
            </form>
          ) : null}

          <section className="glass-panel border border-black/10 p-5 shadow-panel sm:p-6">
            <h3 className="text-xl font-bold text-ink">Участники проекта</h3>
            <div className="mt-4 space-y-3">
              {members.map((member) => (
                <div
                  key={member.user_id}
                  className="flex flex-col items-start gap-3 rounded-[10px] bg-white/70 px-4 py-3 text-sm text-ink sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="font-semibold">{member.full_name}</p>
                    <p className="text-slate/70">
                      {member.email} · роль в проекте{" "}
                      {getRoleLabel(member.role)}
                    </p>
                  </div>
                  {canManageMembers ? (
                    <button
                      className="ui-button-secondary px-3 py-1 text-xs"
                      onClick={() => requestRemoveMember(member.user_id)}
                      type="button"
                    >
                      Удалить
                    </button>
                  ) : null}
                </div>
              ))}
            </div>

            {canManageMembers && availableUsers.length > 0 ? (
              <form className="mt-5 space-y-3" onSubmit={handleAddMember}>
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Пользователь
                  </span>
                  <select
                    className="ui-field"
                    name="member-user"
                    onChange={(event) => setMemberUserId(event.target.value)}
                    value={memberUserId}
                  >
                    <option value="">Выберите пользователя</option>
                    {availableUsers.map((availableUser) => (
                      <option key={availableUser.id} value={availableUser.id}>
                        {availableUser.full_name} (
                        {getRoleLabel(availableUser.role)})
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block">
                  <span className="mb-2 block text-sm font-semibold text-ink/70">
                    Роль в проекте
                  </span>
                  <select
                    className="ui-field"
                    name="member-role"
                    onChange={(event) =>
                      setMemberRole(event.target.value as UserRole)
                    }
                    value={memberRole}
                  >
                    {PROJECT_MEMBER_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {getRoleLabel(role)}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  className="ui-button-secondary"
                  disabled={savingMember || !memberUserId}
                  type="submit"
                >
                  {savingMember ? "Добавляем..." : "Добавить участника"}
                </button>
              </form>
            ) : null}
          </section>
        </div>
      </div>

      <ConfirmDialog
        busy={removingMemberId === memberPendingRemoval?.user_id}
        confirmLabel="Удалить участника"
        description={
          memberPendingRemoval
            ? `Удалить ${memberPendingRemoval.full_name} из проекта? Доступ к проекту будет отозван.`
            : ""
        }
        destructive
        onClose={() => setMemberPendingRemoval(null)}
        onConfirm={handleRemoveMember}
        open={memberPendingRemoval !== null}
        title="Удаление участника проекта"
      />
    </section>
  );
}
