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
import { taskTagsApi, type TaskTagOption } from "@/api/taskTagsApi";
import {
  tasksApi,
  type TaskCreate,
  type TaskRead,
  type TaskStatus,
} from "@/api/tasksApi";
import { usersApi, type UserSummary } from "@/api/usersApi";
import TaskCard from "@/features/tasks/TaskCard";
import { ConfirmDialog } from "@/shared/components/ConfirmDialog";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";
import TagMultiSelect from "@/shared/components/TagMultiSelect";
import { getApiErrorMessage } from "@/shared/lib/apiError";
import { getRoleLabel, getTaskStatusLabel } from "@/shared/lib/locale";
import { useAuthStore } from "@/store/authStore";

const TASK_CREATORS = new Set(["ADMIN", "ANALYST"]);
const PROJECT_MEMBER_ROLES: UserRole[] = [
  "MANAGER",
  "ANALYST",
  "DEVELOPER",
  "TESTER",
  "ADMIN",
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
      <header className="rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white px-6 py-6 sm:px-8">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="max-w-3xl">
            <p className="section-eyebrow">Tasks</p>
            <h2 className="mt-3 text-3xl font-semibold text-[#172b4d] sm:text-4xl">
              {project?.name ?? "Задачи проекта"}
            </h2>
            <p className="mt-4 text-sm leading-7 text-[#44546f]">
              Здесь создаются постановки, назначается команда проекта и
              отслеживается текущий статус задач.
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
                placeholder="Поиск по названию и содержанию"
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
                <option value="">Все статусы</option>
                {[
                  "draft",
                  "needs_rework",
                  "awaiting_approval",
                  "ready_for_dev",
                  "in_progress",
                  "done",
                ].map((status) => (
                  <option key={status} value={status}>
                    {getTaskStatusLabel(status)}
                  </option>
                ))}
              </select>
            </label>
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

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]">
        <div className="space-y-4">
          {tasks.length === 0 ? (
            <div className="rounded-[18px] border border-dashed border-[rgba(9,30,66,0.12)] bg-white px-6 py-8 text-sm leading-7 text-[#626f86]">
              По текущим фильтрам задачи не найдены.
            </div>
          ) : (
            tasks.map((task) => (
              <div key={task.id} className="space-y-3">
                <TaskCard task={task} />
                <Link
                  className="ui-button-secondary"
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
              className="space-y-4 rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white p-5"
              onSubmit={handleCreateTask}
            >
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                  Новая задача
                </p>
                <p className="mt-2 text-sm leading-6 text-[#44546f]">
                  Создайте новую постановку и затем откройте ее в рабочем
                  пространстве аналитика.
                </p>
              </div>
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
                <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
                  Исходное описание
                </span>
                <textarea
                  className="ui-field min-h-32"
                  name="task-content"
                  onChange={(event) =>
                    setTaskForm((current) => ({
                      ...current,
                      content: event.target.value,
                    }))
                  }
                  placeholder="Кратко опишите исходную постановку задачи."
                  value={taskForm.content}
                />
              </label>
              <label className="block">
                <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
                  Теги
                </span>
                <TagMultiSelect
                  helperText={
                    taskTags.length === 0
                      ? "Администратор еще не добавил теги в справочник."
                      : "Теги используются для правил, валидации и поиска."
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
              <button
                className="ui-button-primary"
                disabled={creatingTask}
                type="submit"
              >
                {creatingTask ? "Создаем..." : "Создать задачу"}
              </button>
            </form>
          ) : null}

          <section className="rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white p-5">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                Команда проекта
              </p>
              <h3 className="mt-2 text-xl font-semibold text-[#172b4d]">
                Участники
              </h3>
            </div>

            <div className="mt-4 space-y-3">
              {members.map((member) => (
                <div
                  key={member.user_id}
                  className="flex flex-col items-start gap-3 rounded-[14px] border border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between"
                >
                  <div>
                    <p className="font-medium text-[#172b4d]">
                      {member.full_name}
                    </p>
                    <p className="text-[#44546f]">
                      {member.email} · роль в проекте{" "}
                      {getRoleLabel(member.role)}
                    </p>
                  </div>
                  {canManageMembers ? (
                    <button
                      className="ui-button-ghost px-3 py-1"
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
                  <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
                  <span className="mb-2 block text-sm font-semibold text-[#172b4d]">
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
