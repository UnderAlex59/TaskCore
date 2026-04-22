import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "@/auth/AuthProvider";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import { RoleGuard } from "@/auth/RoleGuard";
import LoginPage from "@/auth/pages/LoginPage";
import AdminLayout from "@/features/admin/AdminLayout";
import RegisterPage from "@/auth/pages/RegisterPage";
import CustomRulesEditor from "@/features/admin/CustomRulesEditor";
import MonitoringPage from "@/features/admin/MonitoringPage";
import ProviderSettingsPage from "@/features/admin/ProviderSettingsPage";
import TaskTagsPage from "@/features/admin/TaskTagsPage";
import ValidationQuestionsPage from "@/features/admin/ValidationQuestionsPage";
import ProfilePage from "@/features/profile/ProfilePage";
import UserList from "@/features/admin/UserList";
import LandingPage from "@/features/landing/LandingPage";
import ProjectList from "@/features/projects/ProjectList";
import TaskChatPage from "@/features/tasks/TaskChatPage";
import TaskCreatePage from "@/features/tasks/TaskCreatePage";
import TaskDetailPage from "@/features/tasks/TaskDetailPage";
import TaskList from "@/features/tasks/TaskList";
import { Layout } from "@/shared/components/Layout";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter
        future={{ v7_relativeSplatPath: true, v7_startTransition: true }}
      >
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<Layout />}>
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/projects" element={<ProjectList />} />
              <Route path="/projects/:projectId/tasks" element={<TaskList />} />
              <Route
                path="/projects/:projectId/tasks/new"
                element={<TaskCreatePage />}
              />
              <Route
                path="/projects/:projectId/tasks/:taskId"
                element={<TaskDetailPage />}
              />
              <Route
                path="/projects/:projectId/tasks/:taskId/chat"
                element={<TaskChatPage />}
              />

              <Route element={<RoleGuard allowedRoles={["ADMIN"]} />}>
                <Route path="/admin" element={<AdminLayout />}>
                  <Route
                    index
                    element={<Navigate to="/admin/monitoring" replace />}
                  />
                  <Route path="monitoring" element={<MonitoringPage />} />
                  <Route
                    path="validation-questions"
                    element={<ValidationQuestionsPage />}
                  />
                  <Route path="task-tags" element={<TaskTagsPage />} />
                  <Route path="providers" element={<ProviderSettingsPage />} />
                  <Route path="users" element={<UserList />} />
                  <Route
                    path="projects/:projectId/rules"
                    element={<CustomRulesEditor />}
                  />
                </Route>
              </Route>
            </Route>
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
