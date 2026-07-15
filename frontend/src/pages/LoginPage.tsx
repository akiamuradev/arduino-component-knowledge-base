import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type SyntheticEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { currentUserQueryKey, useCurrentUser } from "../auth/queries";

interface LoginLocationState {
  from?: string;
}

export function LoginPage() {
  const currentUser = useCurrentUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const location = useLocation();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const mutation = useMutation({
    mutationFn: api.login,
    onSuccess: async ({ user }) => {
      queryClient.setQueryData(currentUserQueryKey, user);
      const state = location.state as LoginLocationState | null;
      const target =
        state?.from?.startsWith("/") === true && !state.from.startsWith("//")
          ? state.from
          : "/";
      await navigate(target, { replace: true });
    },
  });

  if (currentUser.isSuccess) {
    return <Navigate to="/" replace />;
  }

  const submit = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    mutation.mutate({ login, password });
  };
  const errorCode = mutation.error instanceof ApiError ? mutation.error.code : undefined;

  return (
    <main className="login-page">
      <section className="login-copy">
        <p className="eyebrow">Arduino Component Knowledge Base</p>
        <h1>Знания о компонентах в одном контуре</h1>
        <p>Войдите с локальной учётной записью колледжа.</p>
      </section>
      <section className="login-card" aria-labelledby="login-heading">
        <p className="eyebrow">Авторизация</p>
        <h2 id="login-heading">Добро пожаловать</h2>
        <form onSubmit={submit}>
          <label htmlFor="login">Логин</label>
          <input
            autoComplete="username"
            id="login"
            maxLength={100}
            onChange={(event) => {
              setLogin(event.target.value);
            }}
            required
            value={login}
          />
          <label htmlFor="password">Пароль</label>
          <input
            autoComplete="current-password"
            id="password"
            maxLength={128}
            onChange={(event) => {
              setPassword(event.target.value);
            }}
            required
            type="password"
            value={password}
          />
          {mutation.isError ? (
            <p className="form-error" role="alert">
              {errorCode === "authentication_rate_limited"
                ? "Слишком много попыток. Подождите и попробуйте снова."
                : "Не удалось войти. Проверьте данные или повторите позже."}
            </p>
          ) : null}
          <button className="button button--primary" disabled={mutation.isPending} type="submit">
            {mutation.isPending ? "Проверяем…" : "Войти"}
          </button>
        </form>
      </section>
    </main>
  );
}
