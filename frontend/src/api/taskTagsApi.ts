import { apiClient } from "@/api/client";

export interface TaskTagOption {
  id: string;
  name: string;
}

export const taskTagsApi = {
  list: async (projectId: string) =>
    (await apiClient.get<TaskTagOption[]>(`/projects/${projectId}/task-tags`)).data,
  create: async (projectId: string, name: string) =>
    (await apiClient.post<TaskTagOption>(`/projects/${projectId}/task-tags`, { name })).data,
  remove: async (projectId: string, tagId: string) => {
    await apiClient.delete(`/projects/${projectId}/task-tags/${tagId}`);
  },
};
