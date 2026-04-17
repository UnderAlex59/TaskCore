import { apiClient } from "@/api/client";
import type { UserRead, UserRole } from "@/api/authApi";

export type UserSummary = UserRead;

export interface UserUpdatePayload {
  role?: UserRole;
  is_active?: boolean;
}

export interface UserProfileUpdatePayload {
  current_password?: string;
  new_password?: string;
  nickname?: string | null;
  remove_avatar?: boolean;
}

export const usersApi = {
  list: async () => (await apiClient.get<UserSummary[]>("/users")).data,
  update: async (userId: string, payload: UserUpdatePayload) =>
    (await apiClient.patch<UserSummary>(`/users/${userId}`, payload)).data,
  updateMe: async (payload: UserProfileUpdatePayload) =>
    (await apiClient.patch<UserRead>("/users/me", payload)).data,
  uploadAvatar: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return (
      await apiClient.post<UserRead>("/users/me/avatar", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
    ).data;
  },
};
