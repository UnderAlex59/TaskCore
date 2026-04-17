import { apiClient } from "@/api/client";

export interface MessageRead {
  id: string;
  task_id: string;
  author_id: string | null;
  author_name: string | null;
  author_avatar_url: string | null;
  agent_name: string | null;
  message_type: string;
  content: string;
  source_ref: Record<string, unknown> | null;
  created_at: string;
}

export interface MessageCreate {
  content: string;
}

export const chatApi = {
  list: async (taskId: string, params?: { before?: string; limit?: number }) =>
    (await apiClient.get<MessageRead[]>(`/tasks/${taskId}/messages`, { params })).data,
  send: async (taskId: string, payload: MessageCreate) =>
    (await apiClient.post<MessageRead[]>(`/tasks/${taskId}/messages`, payload)).data,
};
