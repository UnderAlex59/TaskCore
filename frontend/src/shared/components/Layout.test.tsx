import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { notificationsApi } from "@/api/notificationsApi";
import { Layout } from "@/shared/components/Layout";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/api/notificationsApi", () => ({
  notificationsApi: {
    connect: vi.fn(() => ({ close: vi.fn() })),
    list: vi.fn(),
    markAllRead: vi.fn(),
    markRead: vi.fn(),
  },
}));

describe("Layout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(notificationsApi.list).mockResolvedValue({
      items: [],
      unread_count: 3,
    });
    useAuthStore.setState({
      accessToken: "token",
      isInitialized: true,
      user: {
        avatar_url: null,
        created_at: new Date().toISOString(),
        email: "user@example.com",
        full_name: "User Example",
        id: "user-1",
        is_active: true,
        nickname: null,
        role: "ANALYST",
      },
    });
  });

  it("loads only unread notifications for the compact center", async () => {
    render(
      <MemoryRouter initialEntries={["/projects"]}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/projects" element={<div>Projects page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(notificationsApi.list).toHaveBeenCalledWith({
        limit: 10,
        unread_only: true,
      });
    });
    expect(screen.getByRole("link", { name: /Уведомления/i })).toHaveAttribute(
      "href",
      "/notifications",
    );
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
  });
});
