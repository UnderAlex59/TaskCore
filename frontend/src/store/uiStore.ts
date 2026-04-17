import { create } from "zustand";

export interface Notification {
  id: string;
  kind: "error" | "info" | "success";
  message: string;
}

interface UiState {
  dismissNotification: (id: string) => void;
  notifications: Notification[];
  pushNotification: (message: string, kind?: Notification["kind"]) => void;
}

export const useUiStore = create<UiState>((set) => ({
  notifications: [],
  pushNotification: (message, kind = "info") =>
    set((state) => ({
      notifications: [...state.notifications, { id: crypto.randomUUID(), message, kind }],
    })),
  dismissNotification: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((item) => item.id !== id),
    })),
}));
