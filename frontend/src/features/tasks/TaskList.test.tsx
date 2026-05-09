import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TaskRead } from "@/api/tasksApi";
import TaskList from "@/features/tasks/TaskList";
import { useAuthStore } from "@/store/authStore";

const projectsApiMock = vi.hoisted(() => ({
  addMember: vi.fn(),
  get: vi.fn(),
  listMembers: vi.fn(),
  remove: vi.fn(),
  removeMember: vi.fn(),
}));

const tasksApiMock = vi.hoisted(() => ({
  list: vi.fn(),
  remove: vi.fn(),
}));

const usersApiMock = vi.hoisted(() => ({
  list: vi.fn(),
}));

vi.mock("@/api/projectsApi", () => ({
  projectsApi: projectsApiMock,
}));

vi.mock("@/api/tasksApi", () => ({
  tasksApi: tasksApiMock,
}));

vi.mock("@/api/usersApi", () => ({
  usersApi: usersApiMock,
}));

const baseTask: TaskRead = {
  id: "task-1",
  project_id: "project-1",
  title: "Синхронизация статусов",
  content: "Обновлять список задач без перезагрузки страницы.",
  tags: [],
  status: "draft",
  created_by: "user-1",
  analyst_id: "user-1",
  reviewer_analyst_id: null,
  developer_id: null,
  tester_id: null,
  reviewer_approved_at: null,
  validation_result: null,
  attachments: [],
  indexed_at: null,
  embeddings_stale: false,
  requires_revalidation: false,
  created_at: new Date("2026-05-07T00:00:00.000Z").toISOString(),
  updated_at: new Date("2026-05-07T00:00:00.000Z").toISOString(),
};

function renderTaskList() {
  return render(
    <MemoryRouter
      future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
      initialEntries={["/projects/project-1/tasks"]}
    >
      <Routes>
        <Route path="/projects/:projectId/tasks" element={<TaskList />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("TaskList", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        id: "user-1",
        email: "admin@example.com",
        full_name: "Администратор",
        nickname: null,
        avatar_url: null,
        role: "ADMIN",
        is_active: true,
        created_at: new Date("2026-05-07T00:00:00.000Z").toISOString(),
      },
      accessToken: "token",
      isInitialized: true,
    });
    projectsApiMock.get.mockResolvedValue({
      id: "project-1",
      name: "Проект задач",
      description: null,
      created_by: "user-1",
      created_at: new Date("2026-05-07T00:00:00.000Z").toISOString(),
      updated_at: new Date("2026-05-07T00:00:00.000Z").toISOString(),
      validation_node_settings: {
        core_rules: true,
        custom_rules: true,
        context_questions: true,
      },
    });
    projectsApiMock.listMembers.mockResolvedValue([]);
    usersApiMock.list.mockResolvedValue([]);
    tasksApiMock.list.mockImplementation(
      async (_projectId: string, params?: { search?: string }) =>
        params?.search ? [] : [baseTask],
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("debounces text search and keeps the task list visible while filtering", async () => {
    renderTaskList();

    expect(await screen.findByText("Синхронизация статусов")).toBeInTheDocument();
    expect(tasksApiMock.list).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("checkbox", { name: "Мои задачи" })).toBeChecked();
    expect(tasksApiMock.list).toHaveBeenLastCalledWith("project-1", {
      participant_id: "user-1",
      search: undefined,
      status: undefined,
      size: 100,
    });

    vi.useFakeTimers();
    fireEvent.change(screen.getByRole("searchbox", { name: "Поиск задач" }), {
      target: { value: "статус" },
    });

    expect(tasksApiMock.list).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Синхронизация статусов")).toBeInTheDocument();
    expect(screen.queryByText("Загрузка задач")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(399);
    });

    expect(tasksApiMock.list).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
      await Promise.resolve();
    });

    expect(tasksApiMock.list).toHaveBeenCalledTimes(2);
    expect(tasksApiMock.list).toHaveBeenLastCalledWith("project-1", {
      participant_id: "user-1",
      search: "статус",
      status: undefined,
      size: 100,
    });
  });

  it("can disable the default my tasks filter", async () => {
    renderTaskList();

    const myTasksFilter = await screen.findByRole("checkbox", {
      name: "Мои задачи",
    });

    await act(async () => {
      fireEvent.click(myTasksFilter);
      await Promise.resolve();
    });

    await waitFor(() => expect(tasksApiMock.list).toHaveBeenCalledTimes(2));
    expect(tasksApiMock.list).toHaveBeenLastCalledWith("project-1", {
      participant_id: undefined,
      search: undefined,
      status: undefined,
      size: 100,
    });
  });
});
