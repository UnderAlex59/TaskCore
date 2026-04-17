import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "@/store/authStore";
import { LoadingSpinner } from "@/shared/components/LoadingSpinner";

export function ProtectedRoute() {
  const isInitialized = useAuthStore((state) => state.isInitialized);
  const user = useAuthStore((state) => state.user);

  if (!isInitialized) {
    return <LoadingSpinner fullscreen />;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
