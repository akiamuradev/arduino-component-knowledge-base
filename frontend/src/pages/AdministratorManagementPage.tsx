import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ChangeEvent, type SyntheticEvent, useState } from "react";

import { api, ApiError } from "../api/client";
import { SplatEmptyState } from "../components/SplatEmptyState";
import { ErrorState, LoadingState } from "../components/AsyncStates";

const administratorsQueryKey = ["administration", "administrators"] as const;

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Не удалось выполнить действие.";
  if (error.code === "administrator_creation_conflict") {
    return "Не удалось создать администратора. Проверьте уникальность логина и пароль.";
  }
  if (error.code === "disable_user_conflict") {
    return "Последнего действующего администратора нельзя отключить.";
  }
  return "Сервер отклонил действие. Обновите список и повторите попытку.";
}

export function AdministratorManagementPage() {
  const queryClient = useQueryClient();
  const administrators = useQuery({
    queryKey: administratorsQueryKey,
    queryFn: api.listAdministrators,
    staleTime: 15_000,
  });
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const createAdministrator = useMutation({
    mutationFn: api.createAdministrator,
    onSuccess: async () => {
      setLogin("");
      setPassword("");
      setConfirmation("");
      setFailure(null);
      setNotice("Учётная запись администратора создана.");
      await queryClient.invalidateQueries({ queryKey: administratorsQueryKey });
    },
    onError: (error) => {
      setNotice(null);
      setFailure(errorMessage(error));
    },
  });
  const disableAdministrator = useMutation({
    mutationFn: api.disableUser,
    onSuccess: async () => {
      setFailure(null);
      setNotice("Учётная запись администратора отключена.");
      await queryClient.invalidateQueries({ queryKey: administratorsQueryKey });
    },
    onError: (error) => {
      setNotice(null);
      setFailure(errorMessage(error));
    },
  });
  const update =
    (setter: (value: string) => void) => (event: ChangeEvent<HTMLInputElement>) => {
      setter(event.target.value);
      setFailure(null);
    };
  const submit = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    if (password !== confirmation) {
      setNotice(null);
      setFailure("Пароли не совпадают.");
      return;
    }
    createAdministrator.mutate({ login, password });
  };

  if (administrators.isPending) return <LoadingState label="Загружаем администраторов…" />;
  if (administrators.isError) {
    return (
      <ErrorState
        title="Администраторы недоступны"
        message="Не удалось загрузить учётные записи. Попробуйте снова."
        onRetry={() => void administrators.refetch()}
      />
    );
  }

  return (
    <section>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Управление доступом</p>
          <h2>Администраторы</h2>
        </div>
        <span className="user-count">Действующих: {administrators.data.total}</span>
      </div>
      <p className="lede">
        Роль администратора назначает только сервер. Последнюю действующую учётную запись
        отключить нельзя.
      </p>
      {failure === null ? null : <p className="management-message management-message--error" role="alert">{failure}</p>}
      {notice === null ? null : <p className="management-message management-message--success" role="status">{notice}</p>}
      <form className="editor-form temporary-editor-form" onSubmit={submit}>
        <fieldset>
          <legend>Создать администратора</legend>
          <div className="form-grid">
            <label>
              Логин
              <input
                autoComplete="off"
                maxLength={100}
                minLength={3}
                onChange={update(setLogin)}
                required
                value={login}
              />
            </label>
            <label>
              Новый пароль
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={12}
                onChange={update(setPassword)}
                required
                type="password"
                value={password}
              />
            </label>
            <label>
              Подтверждение пароля
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={12}
                onChange={update(setConfirmation)}
                required
                type="password"
                value={confirmation}
              />
            </label>
          </div>
          <button className="button button--primary" disabled={createAdministrator.isPending} type="submit">
            {createAdministrator.isPending ? "Создаём…" : "Создать администратора"}
          </button>
        </fieldset>
      </form>
      <div className="managed-users" aria-label="Список администраторов">
        {administrators.data.items.length === 0 ? (
          <SplatEmptyState
            icon="◇"
            title="Администраторов не найдено"
            description="Проверьте состояние системы и повторите запрос."
          />
        ) : null}
        {administrators.data.items.map((administrator) => (
          <article className="managed-user-card" key={administrator.id}>
            <div className="managed-user-card__identity">
              <span className="account__avatar" aria-hidden="true">
                {administrator.login.slice(0, 2).toUpperCase()}
              </span>
              <span><strong>{administrator.login}</strong><small>Действующий администратор</small></span>
            </div>
            <div className="managed-user-card__state">
              <span className="status-badge status-badge--published">Администратор</span>
            </div>
            <div className="managed-user-card__actions">
              <button
                className="button button--danger"
                disabled={disableAdministrator.isPending}
                onClick={() => {
                  if (window.confirm(`Отключить администратора «${administrator.login}»?`)) {
                    disableAdministrator.mutate(administrator.id);
                  }
                }}
                type="button"
              >
                Отключить
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
