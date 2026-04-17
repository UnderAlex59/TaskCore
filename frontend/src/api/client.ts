import axios, { type AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";

import { useAuthStore } from "@/store/authStore";

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

type TokenResponse = {
  access_token: string;
};

type RetriableConfig = InternalAxiosRequestConfig & { _retry?: boolean };

type QueueItem = {
  reject: (reason?: unknown) => void;
  request: RetriableConfig;
  resolve: (value: unknown) => void;
};

let isRefreshing = false;
let refreshQueue: QueueItem[] = [];

function setAuthorizationHeader(config: RetriableConfig, token: string) {
  const headers = (config.headers ?? {}) as Record<string, string>;
  headers.Authorization = `Bearer ${token}`;
  config.headers = headers as RetriableConfig["headers"];
}

function flushQueue(error: unknown, token: string | null) {
  for (const item of refreshQueue) {
    if (error || token === null) {
      item.reject(error);
      continue;
    }

    setAuthorizationHeader(item.request, token);
    item.resolve(apiClient(item.request));
  }

  refreshQueue = [];
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    setAuthorizationHeader(config as RetriableConfig, token);
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as RetriableConfig | undefined;

    if (
      error.response?.status !== 401 ||
      original === undefined ||
      original._retry ||
      original.url?.includes("/auth/")
    ) {
      return Promise.reject(error);
    }

    original._retry = true;

    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        refreshQueue.push({ resolve, reject, request: original });
      });
    }

    isRefreshing = true;

    try {
      const { data } = await apiClient.post<TokenResponse>("/auth/refresh");
      const newToken = data.access_token;
      useAuthStore.getState().setAccessToken(newToken);
      flushQueue(null, newToken);
      setAuthorizationHeader(original, newToken);
      return apiClient(original);
    } catch (refreshError) {
      flushQueue(refreshError, null);
      useAuthStore.getState().logout();
      window.location.href = "/login";
      return Promise.reject(refreshError);
    } finally {
      isRefreshing = false;
    }
  },
);
