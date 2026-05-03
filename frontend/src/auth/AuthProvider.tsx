import { useEffect } from "react";

import { authApi } from "@/api/authApi";
import { useAuthStore } from "@/store/authStore";

const PUBLIC_AUTH_PATHS = new Set(["/", "/login", "/register"]);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const logout = useAuthStore((state) => state.logout);
  const setAccessToken = useAuthStore((state) => state.setAccessToken);
  const setInitialized = useAuthStore((state) => state.setInitialized);
  const setUser = useAuthStore((state) => state.setUser);

  useEffect(() => {
    let active = true;

    async function initAuth() {
      const currentPath = window.location.pathname;
      if (PUBLIC_AUTH_PATHS.has(currentPath)) {
        setInitialized();
        return;
      }

      try {
        const { data: tokenData } = await authApi.refresh();
        if (!active) {
          return;
        }

        setAccessToken(tokenData.access_token);
        const { data: userData } = await authApi.me();
        if (!active) {
          return;
        }
        setUser(userData);
      } catch {
        if (active) {
          logout();
        }
      } finally {
        if (active) {
          setInitialized();
        }
      }
    }

    void initAuth();

    return () => {
      active = false;
    };
  }, [logout, setAccessToken, setInitialized, setUser]);

  return <>{children}</>;
}
