import { API_BASE, apiClient } from "@/api/client";

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

export interface ChatRealtimeEvent {
  messages: MessageRead[];
  type: "messages.created";
}

function getWebSocketBaseUrl() {
  if (API_BASE.startsWith("ws://") || API_BASE.startsWith("wss://")) {
    return API_BASE;
  }

  if (API_BASE.startsWith("http://") || API_BASE.startsWith("https://")) {
    const url = new URL(API_BASE);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }

  const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const basePath = API_BASE.startsWith("/") ? API_BASE : `/${API_BASE}`;
  return `${wsProtocol}//${window.location.host}${basePath}`;
}

function buildRealtimeUrl(taskId: string, token: string) {
  const baseUrl = getWebSocketBaseUrl();
  const socketUrl = new URL(
    `tasks/${taskId}/messages/ws`,
    baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`,
  );
  socketUrl.searchParams.set("token", token);
  return socketUrl.toString();
}

export const chatApi = {
  list: async (taskId: string, params?: { before?: string; limit?: number }) =>
    (await apiClient.get<MessageRead[]>(`/tasks/${taskId}/messages`, { params })).data,
  send: async (taskId: string, payload: MessageCreate) =>
    (await apiClient.post<MessageRead[]>(`/tasks/${taskId}/messages`, payload)).data,
  connect: (taskId: string, token: string) =>
    new WebSocket(buildRealtimeUrl(taskId, token)),
};
