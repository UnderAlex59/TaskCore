import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { RoleGuard } from "@/auth/RoleGuard";
import { useAuthStore } from "@/store/authStore";

describe("route guards", () => {
  it("redirects unauthenticated users to login", () => {
    useAuthStore.setState({ user: null, accessToken: null, isInitialized: true });

    render(
      <MemoryRouter
        future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
        initialEntries={["/projects"]}
      >
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route element={<ProtectedRoute />}>
            <Route path="/projects" element={<div>Projects page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Login page")).toBeInTheDocument();
  });

  it("allows only configured roles into guarded routes", () => {
    useAuthStore.setState({
      user: {
        id: "1",
        email: "admin@example.com",
        full_name: "Admin User",
        nickname: null,
        avatar_url: null,
        role: "ADMIN",
        is_active: true,
        created_at: new Date().toISOString(),
      },
      accessToken: "token",
      isInitialized: true,
    });

    render(
      <MemoryRouter
        future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
        initialEntries={["/admin/users"]}
      >
        <Routes>
          <Route element={<RoleGuard allowedRoles={["ADMIN"]} />}>
            <Route path="/admin/users" element={<div>Admin page</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Admin page")).toBeInTheDocument();
  });
});
