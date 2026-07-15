import { Navigate, Outlet, useLocation } from "react-router-dom";

import type { Role } from "../api/contracts";
import { ApiError } from "../api/client";
import { useCurrentUser } from "../auth/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";

export function RequireAuthenticated() {
  const location = useLocation();
  const currentUser = useCurrentUser();

  if (currentUser.isPending) {
    return <LoadingState label="Проверяем сессию…" />;
  }
  if (currentUser.isError) {
    if (currentUser.error instanceof ApiError && currentUser.error.status === 401) {
      return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    }
    return (
      <ErrorState
        message="Backend не подтвердил сессию. Проверьте соединение и повторите запрос."
        onRetry={() => void currentUser.refetch()}
      />
    );
  }
  return <Outlet />;
}

export function RequireRole({ role }: { role: Role }) {
  return <RequireAnyRole roles={[role]} />;
}

export function RequireAnyRole({ roles }: { roles: Role[] }) {
  const currentUser = useCurrentUser();
  if (currentUser.isPending) {
    return <LoadingState label="Проверяем права…" />;
  }
  if (currentUser.isError) {
    return <Navigate to="/login" replace />;
  }
  if (!roles.some((role) => currentUser.data.roles.includes(role))) {
    return <Navigate to="/forbidden" replace />;
  }
  return <Outlet />;
}
