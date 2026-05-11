import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  notificationsApi,
  type NotificationRead,
} from "@/api/notificationsApi";
import NotificationsPage from "@/features/notifications/NotificationsPage";

vi.mock("@/api/notificationsApi", () => ({
  notificationsApi: {
    list: vi.fn(),
    markAllRead: vi.fn(),
    markRead: vi.fn(),
  },
}));

const unreadNotification: NotificationRead = {
  body: "Проверьте постановку задачи.",
  created_at: "2026-05-09T08:00:00.000Z",
  id: "notification-1",
  message_id: null,
  metadata: null,
  priority: "important",
  project_id: "project-1",
  read_at: null,
  task_id: "task-1",
  title: "Срочно проверить задачу",
  type: "task_assigned",
  user_id: "user-1",
};

const mentionNotification: NotificationRead = {
  ...unreadNotification,
  body: "Вас упомянули в обсуждении.",
  id: "notification-2",
  priority: "normal",
  title: "Упоминание в чате",
  type: "chat_mention",
};

describe("NotificationsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsApi.list).mockResolvedValue({
      items: [unreadNotification, mentionNotification],
      unread_count: 2,
    });
    vi.mocked(notificationsApi.markRead).mockResolvedValue({
      ...unreadNotification,
      read_at: "2026-05-09T08:10:00.000Z",
    });
    vi.mocked(notificationsApi.markAllRead).mockResolvedValue(undefined);
  });

  it("requests notifications with selected filters", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(notificationsApi.list).toHaveBeenCalledWith({
        limit: 100,
        read_state: "all",
      });
    });

    await user.click(screen.getByRole("button", { name: "Непрочитанные" }));
    await user.selectOptions(screen.getByLabelText("Важность"), "important");
    await user.selectOptions(screen.getByLabelText("Тип"), "chat_mention");
    await user.type(screen.getByLabelText("Поиск"), "задачу");

    await waitFor(() => {
      expect(notificationsApi.list).toHaveBeenLastCalledWith(
        expect.objectContaining({
          limit: 100,
          priority: "important",
          read_state: "unread",
          search: "задачу",
          type: "chat_mention",
        }),
      );
    });
  });

  it("marks all visible unread notifications as read", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <NotificationsPage />
      </MemoryRouter>,
    );

    await screen.findByText("Срочно проверить задачу");
    await user.click(screen.getByRole("button", { name: "Отметить найденные" }));

    await waitFor(() => {
      expect(notificationsApi.markRead).toHaveBeenCalledWith("notification-1");
      expect(notificationsApi.markRead).toHaveBeenCalledWith("notification-2");
    });
  });
});
