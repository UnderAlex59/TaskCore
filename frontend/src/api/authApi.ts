import { apiClient } from "@/api/client";

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export type UserRole = "ADMIN" | "ANALYST" | "DEVELOPER" | "TESTER" | "MANAGER";

export interface UserRead {
  id: string;
  email: string;
  full_name: string;
  nickname: string | null;
  avatar_url: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export const authApi = {
  login: (email: string, password: string) =>
    apiClient.post<TokenResponse>("/auth/login", { email, password }),
  register: (email: string, password: string, full_name: string) =>
    apiClient.post<UserRead>("/auth/register", { email, password, full_name }),
  refresh: () => apiClient.post<TokenResponse>("/auth/refresh"),
  logout: () => apiClient.post<void>("/auth/logout"),
  me: () => apiClient.get<UserRead>("/auth/me"),
};
