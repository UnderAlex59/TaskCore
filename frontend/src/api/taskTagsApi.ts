import { apiClient } from "@/api/client";

export interface TaskTagOption {
  id: string;
  name: string;
}

export const taskTagsApi = {
  list: async () => (await apiClient.get<TaskTagOption[]>("/task-tags")).data,
};
