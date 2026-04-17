import { create } from "zustand";

import type { UserRead } from "@/api/authApi";

export interface AuthState {
  accessToken: string | null;
  isInitialized: boolean;
  logout: () => void;
  setAccessToken: (token: string | null) => void;
  setInitialized: () => void;
  setUser: (user: UserRead | null) => void;
  user: UserRead | null;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  isInitialized: false,
  setUser: (user) => set({ user }),
  setAccessToken: (token) => set({ accessToken: token }),
  setInitialized: () => set({ isInitialized: true }),
  logout: () => set({ user: null, accessToken: null }),
}));
