import { API_BASE, apiClient } from "@/api/client";

export interface NotificationRead {
  id: string;
  user_id: string;
  type: string;
  priority: "normal" | "important";
  title: string;
  body: string;
  project_id: string | null;
  task_id: string | null;
  message_id: string | null;
  metadata: Record<string, unknown> | null;
  read_at: string | null;
  created_at: string;
}

export interface NotificationPageRead {
  items: NotificationRead[];
  unread_count: number;
}

export interface ChatUnreadRead {
  task_id: string;
  unread_count: number;
  last_read_at: string | null;
}

export interface NotificationSettingsRead {
  telegram_important_enabled: boolean;
  telegram_normal_enabled: boolean;
  telegram_linked: boolean;
  telegram_username: string | null;
}

export interface NotificationRealtimeEvent {
  notifications?: NotificationRead[];
  task_id?: string;
  type: "notifications.created" | "chat.unread.changed";
  unread_count?: number;
}

export interface TelegramLinkTokenRead {
  token: string;
  expires_at: string;
  deep_link: string | null;
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

function buildNotificationsRealtimeUrl(token: string) {
  const baseUrl = getWebSocketBaseUrl();
  const socketUrl = new URL(
    "notifications/ws",
    baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`,
  );
  socketUrl.searchParams.set("token", token);
  return socketUrl.toString();
}

export const notificationsApi = {
  list: async (params?: { limit?: number; unread_only?: boolean }) =>
    (await apiClient.get<NotificationPageRead>("/notifications", { params }))
      .data,
  markRead: async (notificationId: string) =>
    (
      await apiClient.patch<NotificationRead>(
        `/notifications/${notificationId}/read`,
      )
    ).data,
  markAllRead: async () => {
    await apiClient.post("/notifications/read-all");
  },
  getSettings: async () =>
    (
      await apiClient.get<NotificationSettingsRead>(
        "/users/me/notification-settings",
      )
    ).data,
  updateSettings: async (payload: {
    telegram_important_enabled?: boolean;
    telegram_normal_enabled?: boolean;
  }) =>
    (
      await apiClient.patch<NotificationSettingsRead>(
        "/users/me/notification-settings",
        payload,
      )
    ).data,
  createTelegramLinkToken: async () =>
    (
      await apiClient.post<TelegramLinkTokenRead>(
        "/users/me/telegram-link-token",
      )
    ).data,
  unlinkTelegram: async () => {
    await apiClient.delete("/users/me/telegram");
  },
  getTaskUnread: async (taskId: string) =>
    (await apiClient.get<ChatUnreadRead>(`/tasks/${taskId}/chat-unread`)).data,
  markTaskChatRead: async (taskId: string) =>
    (await apiClient.post<ChatUnreadRead>(`/tasks/${taskId}/chat-read`)).data,
  requestAnalyst: async (taskId: string, messageId: string) =>
    (
      await apiClient.post<NotificationRead>(
        `/tasks/${taskId}/messages/${messageId}/request-analyst`,
      )
    ).data,
  connect: (token: string) =>
    new WebSocket(buildNotificationsRealtimeUrl(token)),
};
