import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "@/store/authStore";

interface Props {
  allowedRoles: string[];
}

export function RoleGuard({ allowedRoles }: Props) {
  const user = useAuthStore((state) => state.user);

  if (!user || !allowedRoles.includes(user.role)) {
    return <Navigate to="/projects" replace />;
  }

  return <Outlet />;
}
