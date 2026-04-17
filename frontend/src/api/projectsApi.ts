import { apiClient } from "@/api/client";
import type { UserRole } from "@/api/authApi";

export interface ProjectRead {
  id: string;
  name: string;
  description: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
}

export interface ProjectMemberRead {
  project_id: string;
  user_id: string;
  role: UserRole;
  joined_at: string;
  full_name: string;
  email: string;
  global_role: UserRole;
}

export interface CustomRuleRead {
  id: string;
  project_id: string;
  title: string;
  description: string;
  applies_to_tags: string[];
  is_active: boolean;
  created_by: string;
  created_at: string;
}

export interface CustomRuleCreate {
  title: string;
  description: string;
  applies_to_tags: string[];
  is_active: boolean;
}

export const projectsApi = {
  list: async () => (await apiClient.get<ProjectRead[]>("/projects")).data,
  create: async (payload: ProjectCreate) => (await apiClient.post<ProjectRead>("/projects", payload)).data,
  get: async (projectId: string) => (await apiClient.get<ProjectRead>(`/projects/${projectId}`)).data,
  update: async (projectId: string, payload: Partial<ProjectCreate>) =>
    (await apiClient.patch<ProjectRead>(`/projects/${projectId}`, payload)).data,
  remove: async (projectId: string) => {
    await apiClient.delete(`/projects/${projectId}`);
  },
  listMembers: async (projectId: string) =>
    (await apiClient.get<ProjectMemberRead[]>(`/projects/${projectId}/members`)).data,
  addMember: async (projectId: string, payload: { user_id: string; role: UserRole }) =>
    (await apiClient.post<ProjectMemberRead>(`/projects/${projectId}/members`, payload)).data,
  removeMember: async (projectId: string, userId: string) => {
    await apiClient.delete(`/projects/${projectId}/members/${userId}`);
  },
  listRules: async (projectId: string) =>
    (await apiClient.get<CustomRuleRead[]>(`/projects/${projectId}/rules`)).data,
  createRule: async (projectId: string, payload: CustomRuleCreate) =>
    (await apiClient.post<CustomRuleRead>(`/projects/${projectId}/rules`, payload)).data,
  updateRule: async (projectId: string, ruleId: string, payload: Partial<CustomRuleCreate>) =>
    (await apiClient.patch<CustomRuleRead>(`/projects/${projectId}/rules/${ruleId}`, payload)).data,
  removeRule: async (projectId: string, ruleId: string) => {
    await apiClient.delete(`/projects/${projectId}/rules/${ruleId}`);
  },
};
