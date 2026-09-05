import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, type SyntheticEvent, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { currentUserQueryKey, useCurrentUser } from "../auth/queries";
import { BrandMark } from "../components/BrandMark";
import { type OledState, OledLoginDisplay } from "../components/OledLoginDisplay";
import { ThemeToggle } from "../components/ThemeToggle";
import { PRODUCT_BRAND } from "../config/brand";

export function RegisterPage() {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: api.register,
    onSuccess: async ({ user }) => {
      queryClient.setQueryData(currentUserQueryKey, user);
      await navigate("/", { replace: true });
    },
  });

  if (currentUser.isSuccess) {
    return <Navigate to="/" replace />;
  }

  const update =
    (setter: (value: string) => void) => (event: ChangeEvent<HTMLInputElement>) => {
      setter(event.target.value);
      setLocalError(null);
      if (mutation.isError) mutation.reset();
    };
  const submit = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    if (password !== confirmation) {
      setLocalError("Пароли не совпадают.");
      return;
    }
    mutation.mutate({ login, password });
  };
  const errorCode = mutation.error instanceof ApiError ? mutation.error.code : undefined;
  const serverError =
    errorCode === "login_already_exists"
      ? "Этот логин уже занят. Выберите другой."
      : mutation.isError
        ? "Не удалось создать аккаунт. Проверьте логин и пароль."
        : null;
  const oledState: OledState = mutation.isPending
    ? "submitting"
    : mutation.isSuccess
      ? "success"
      : mutation.isError || localError !== null
        ? "error"
        : "idle";

  return (
    <main className="login-page">
      <section className="login-hero">
        <div className="login-brand"><BrandMark /><strong>{PRODUCT_BRAND.shortName}</strong></div>
        <div className="login-copy__content">
          <p className="eyebrow">Учебная база знаний</p>
          <h1>Создайте доступ к каталогу</h1>
          <p>Новая учётная запись получает только безопасный доступ студента.</p>
        </div>
        <OledLoginDisplay state={oledState} />
      </section>
      <section className="login-panel">
        <div className="login-panel__theme"><ThemeToggle /></div>
        <div className="login-card" aria-labelledby="register-heading">
          <div className="login-card__heading">
            <p className="eyebrow">Самостоятельная регистрация</p>
            <h2 id="register-heading">Создать аккаунт</h2>
            <p>Укажите логин и пароль. Дополнительные данные не требуются.</p>
          </div>
          <form onSubmit={submit}>
            <label htmlFor="register-login">Логин</label>
            <input
              autoComplete="username"
              id="register-login"
              maxLength={100}
              minLength={3}
              onChange={update(setLogin)}
              required
              value={login}
            />
            <label htmlFor="register-password">Пароль</label>
            <input
              autoComplete="new-password"
              id="register-password"
              maxLength={128}
              minLength={12}
              onChange={update(setPassword)}
              required
              type="password"
              value={password}
            />
            <label htmlFor="register-confirmation">Подтверждение пароля</label>
            <input
              autoComplete="new-password"
              id="register-confirmation"
              maxLength={128}
              minLength={12}
              onChange={update(setConfirmation)}
              required
              type="password"
              value={confirmation}
            />
            <div aria-live="polite" className="auth-announcement">
              {mutation.isPending ? "Создаём безопасную учётную запись." : ""}
            </div>
            {localError === null && serverError === null ? null : (
              <p className="form-error" role="alert">{localError ?? serverError}</p>
            )}
            <button className="button button--primary" disabled={mutation.isPending} type="submit">
              {mutation.isPending ? "Создаём…" : "Создать аккаунт"}
            </button>
          </form>
          <p className="auth-switch">Уже есть аккаунт? <Link to="/login">Войти</Link></p>
          <p className="login-security"><span aria-hidden="true">●</span> Права администратора через регистрацию получить нельзя.</p>
        </div>
      </section>
    </main>
  );
}
