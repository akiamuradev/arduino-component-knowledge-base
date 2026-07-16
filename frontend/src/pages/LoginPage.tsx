import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, type SyntheticEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { currentUserQueryKey, useCurrentUser } from "../auth/queries";
import { BrandMark } from "../components/BrandMark";
import { type OledState, OledLoginDisplay } from "../components/OledLoginDisplay";
import { ThemeToggle } from "../components/ThemeToggle";
import { PRODUCT_BRAND } from "../config/brand";

interface LoginLocationState {
  from?: string;
}

type AccessMode = "student" | "admin";

export function LoginPage() {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [accessMode, setAccessMode] = useState<AccessMode | null>(null);
  const state = location.state as LoginLocationState | null;
  const target =
    state?.from?.startsWith("/") === true && !state.from.startsWith("//")
      ? state.from
      : "/";
  const mutation = useMutation({
    mutationFn: api.login,
    onSuccess: async ({ user }) => {
      queryClient.setQueryData(currentUserQueryKey, user);
      await navigate(target, { replace: true });
    },
  });

  if (currentUser.isSuccess) {
    return <Navigate to={target} replace />;
  }

  const submit = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    mutation.mutate({ login, password });
  };
  const errorCode = mutation.error instanceof ApiError ? mutation.error.code : undefined;
  const oledState: OledState = mutation.isPending
    ? "submitting"
    : mutation.isSuccess
      ? "success"
      : mutation.isError
        ? "error"
        : accessMode === "student"
          ? "student_selected"
          : accessMode === "admin"
            ? "admin_selected"
            : "idle";
  const updateCredential = (field: "login" | "password") => (event: ChangeEvent<HTMLInputElement>) => {
    if (mutation.isError) mutation.reset();
    if (field === "login") setLogin(event.target.value);
    else setPassword(event.target.value);
  };

  return (
    <main className="login-page">
      <section className="login-hero">
        <div className="login-brand"><BrandMark /><strong>{PRODUCT_BRAND.shortName}</strong></div>
        <div className="login-copy__content">
          <p className="eyebrow">Учебная база знаний</p>
          <h1>От детали на столе — к работающему проекту</h1>
          <p>Проверенные карточки компонентов, совместимость и учебные примеры в едином контуре колледжа.</p>
        </div>
        <OledLoginDisplay state={oledState} />
      </section>
      <section className="login-panel">
        <div className="login-panel__theme"><ThemeToggle /></div>
        <div className="login-card" aria-labelledby="login-heading">
        <div className="login-card__heading">
          <p className="eyebrow">Локальная учётная запись</p>
          <h2 id="login-heading">Вход в систему</h2>
          <p>Используйте данные, выданные администратором.</p>
        </div>
        <form onSubmit={submit}>
          <fieldset className="access-mode">
            <legend>Режим доступа</legend>
            <label><input checked={accessMode === "student"} name="access-mode" onChange={() => { if (mutation.isError) mutation.reset(); setAccessMode("student"); }} type="radio" /><span><strong>Студент</strong><small>Каталог и учебные материалы</small></span></label>
            <label><input checked={accessMode === "admin"} name="access-mode" onChange={() => { if (mutation.isError) mutation.reset(); setAccessMode("admin"); }} type="radio" /><span><strong>Редакция</strong><small>Вход для преподавателя</small></span></label>
          </fieldset>
          <label htmlFor="login">Логин</label>
          <input
            autoComplete="username"
            id="login"
            maxLength={100}
            onChange={updateCredential("login")}
            required
            placeholder="Ваш логин"
            value={login}
          />
          <label htmlFor="password">Пароль</label>
          <input
            autoComplete="current-password"
            id="password"
            maxLength={128}
            onChange={updateCredential("password")}
            required
            placeholder="••••••••••••"
            type="password"
            value={password}
          />
          <div aria-live="polite" className="auth-announcement">
            {mutation.isPending ? "Проверяем учётные данные." : mutation.isSuccess ? "Вход выполнен." : ""}
          </div>
          {mutation.isError ? (
            <p className="form-error" role="alert" aria-live="assertive">
              {errorCode === "authentication_rate_limited"
                ? "Слишком много попыток. Подождите и попробуйте снова."
                : "Не удалось войти. Проверьте данные или повторите позже."}
            </p>
          ) : null}
          <button className="button button--primary" disabled={mutation.isPending} type="submit">
            {mutation.isPending ? "Проверяем…" : "Войти"}
          </button>
        </form>
          <p className="login-security"><span aria-hidden="true">●</span> Права определяет backend после входа.</p>
        </div>
        <footer className="login-footer">
          <span>Developed by <a aria-label="GitHub автора akiamuradev (откроется в новой вкладке)" href={PRODUCT_BRAND.authorUrl} target="_blank" rel="noopener noreferrer">{PRODUCT_BRAND.authorName}</a></span>
          <span>{PRODUCT_BRAND.copyright}</span>
        </footer>
      </section>
    </main>
  );
}
