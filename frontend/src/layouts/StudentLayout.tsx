import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { currentUserQueryKey, useCurrentUser } from "../auth/queries";

export function StudentLayout() {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: currentUserQueryKey });
      await navigate("/login", { replace: true });
    },
  });

  if (currentUser.data === undefined) {
    return null;
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <NavLink className="brand" to="/">
          <span className="brand__mark" aria-hidden="true">A</span>
          <span>
            <strong>Component KB</strong>
            <small>Arduino-справочник колледжа</small>
          </span>
        </NavLink>
        <nav aria-label="Основная навигация">
          <NavLink to="/">Каталог</NavLink>
          {currentUser.data.roles.some((role) =>
            role === "teacher" || role === "administrator") ? (
            <NavLink to="/admin">Редакция</NavLink>
          ) : null}
        </nav>
        <div className="account">
          <span>{currentUser.data.display_name}</span>
          <button
            className="button button--quiet"
            disabled={logout.isPending}
            onClick={() => {
              logout.mutate();
            }}
            type="button"
          >
            {logout.isPending ? "Выходим…" : "Выйти"}
          </button>
        </div>
      </header>
      {logout.isError ? (
        <div className="inline-error" role="alert">
          Не удалось завершить сессию. Повторите попытку.
        </div>
      ) : null}
      <main className="page"><Outlet /></main>
    </div>
  );
}
