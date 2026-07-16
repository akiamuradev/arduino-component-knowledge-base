import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SyntheticEvent } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { api } from "../api/client";
import { currentUserQueryKey, useCurrentUser } from "../auth/queries";
import { PRODUCT_BRAND } from "../config/brand";
import { BrandMark } from "./BrandMark";
import { ThemeToggle } from "./ThemeToggle";

export function AppHeader() {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const search = location.pathname === "/" ? new URLSearchParams(location.search).get("q") ?? "" : "";
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
      queryClient.removeQueries({ queryKey: currentUserQueryKey });
      await navigate("/login", { replace: true });
    },
  });

  if (currentUser.data === undefined) return null;

  const canEdit = currentUser.data.roles.some(
    (role) => role === "teacher" || role === "administrator",
  );
  const primaryRole = currentUser.data.roles.includes("administrator")
    ? "Администратор"
    : currentUser.data.roles.includes("teacher")
      ? "Преподаватель"
      : "Студент";
  const avatarLetter = currentUser.data.display_name.trim().charAt(0).toUpperCase() || "A";
  const submitSearch = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    const entry = new FormData(event.currentTarget).get("q");
    const value = typeof entry === "string" ? entry.trim() : "";
    void navigate(value === "" ? "/" : `/?q=${encodeURIComponent(value)}`);
  };

  return (
    <>
      <header className="topbar">
        <NavLink className="brand" to="/" aria-label={`${PRODUCT_BRAND.shortName}: каталог`}>
          <BrandMark />
          <span className="brand__copy"><strong>{PRODUCT_BRAND.shortName}</strong><small>Component Knowledge Base</small></span>
        </NavLink>
        <form className="global-search" role="search" onSubmit={submitSearch}>
          <span aria-hidden="true">⌕</span>
          <label className="sr-only" htmlFor="global-search">Глобальный поиск</label>
          <input defaultValue={search} id="global-search" key={search} maxLength={100} name="q" placeholder="Найти компонент…" type="search" />
        </form>
        <nav className="topbar__nav" aria-label="Основная навигация">
          <NavLink to="/">Каталог</NavLink>
          {canEdit ? <NavLink to="/admin">Редакция</NavLink> : null}
        </nav>
        <ThemeToggle />
        <details className="user-menu">
          <summary aria-label={`Меню пользователя: ${currentUser.data.display_name}`}>
            <span className="account__avatar" aria-hidden="true">{avatarLetter}</span>
            <span className="account__copy"><strong>{currentUser.data.display_name}</strong><small>{primaryRole}</small></span>
            <span aria-hidden="true">⌄</span>
          </summary>
          <div className="user-menu__panel">
            <span><strong>{currentUser.data.display_name}</strong><small>{currentUser.data.login}</small></span>
            <button className="button button--quiet" disabled={logout.isPending} onClick={() => { logout.mutate(); }} type="button">
              {logout.isPending ? "Выходим…" : "Выйти"}
            </button>
          </div>
        </details>
      </header>
      {logout.isError ? <div className="inline-error" role="alert">Не удалось завершить сессию. Повторите попытку.</div> : null}
    </>
  );
}
