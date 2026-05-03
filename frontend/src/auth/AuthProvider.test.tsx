import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { authApi } from "@/api/authApi";
import { AuthProvider } from "@/auth/AuthProvider";
import { useAuthStore } from "@/store/authStore";

vi.mock("@/api/authApi", () => ({
  authApi: {
    refresh: vi.fn().mockRejectedValue(new Error("no refresh token")),
    me: vi.fn(),
  },
}));

function StatusProbe() {
  const isInitialized = useAuthStore((state) => state.isInitialized);
  return <span>{isInitialized ? "initialized" : "pending"}</span>;
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.history.pushState({}, "", "/projects");
  });

  it("marks auth as initialized even when refresh fails", async () => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      isInitialized: false,
    });

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("initialized")).toBeInTheDocument();
    });
  });

  it("does not request refresh on public pages", async () => {
    window.history.pushState({}, "", "/login");
    useAuthStore.setState({
      user: null,
      accessToken: null,
      isInitialized: false,
    });

    render(
      <AuthProvider>
        <StatusProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("initialized")).toBeInTheDocument();
    });
    expect(authApi.refresh).not.toHaveBeenCalled();
  });
});
