import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SyntheticEvent, useState } from "react";

import type { ManagedUser } from "../api/contracts";
import { api, ApiError } from "../api/client";
import { ErrorState, LoadingState } from "../components/AsyncStates";

const managedUsersQueryKey = ["administration", "users"] as const;

function localDateTimeAfter(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  date.setSeconds(0, 0);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function toIso(localValue: string): string | null {
  const value = new Date(localValue);
  return Number.isNaN(value.getTime()) ? null : value.toISOString();
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function errorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) {
    return "Не удалось выполнить действие. Повторите попытку.";
  }
  const messages: Record<string, string> = {
    editor_creation_conflict:
      "Не удалось создать редактора. Проверьте уникальность логина, пароль и срок доступа.",
    editor_grant_conflict:
      "Не удалось назначить редактора. Проверьте статус пользователя и будущую дату окончания.",
    editor_revoke_conflict: "Роль редактора уже не действует или пользователь недоступен.",
    disable_user_conflict: "Нельзя заблокировать эту учётную запись.",
  };
  return messages[error.code] ?? "Сервер отклонил действие. Обновите список и повторите попытку.";
}

function accessLabel(user: ManagedUser): string {
  if (user.roles.includes("administrator")) return "Администратор";
  if (user.roles.includes("editor")) return "Редактор базы";
  if (user.roles.includes("teacher")) return "Преподаватель";
  return "Студент";
}

export function UserManagementPage() {
  const queryClient = useQueryClient();
  const users = useQuery({
    queryKey: managedUsersQueryKey,
    queryFn: api.listUsers,
    staleTime: 15_000,
  });
  const [login, setLogin] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [newEditorExpiry, setNewEditorExpiry] = useState(() => localDateTimeAfter(7));
  const [grantExpiry, setGrantExpiry] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: managedUsersQueryKey });
  };
  const createEditor = useMutation({
    mutationFn: api.createEditor,
    onSuccess: async () => {
      setLogin("");
      setDisplayName("");
      setPassword("");
      setNewEditorExpiry(localDateTimeAfter(7));
      setFailure(null);
      setNotice("Учётная запись временного редактора создана.");
      await refresh();
    },
    onError: (error) => {
      setNotice(null);
      setFailure(errorMessage(error));
    },
  });
  const grantEditor = useMutation({
    mutationFn: ({ userId, expiresAt }: { userId: string; expiresAt: string }) =>
      api.grantEditor(userId, expiresAt),
    onSuccess: async () => {
      setFailure(null);
      setNotice("Временный доступ редактора назначен.");
      await refresh();
    },
    onError: (error) => {
      setNotice(null);
      setFailure(errorMessage(error));
    },
  });
  const revokeEditor = useMutation({
    mutationFn: api.revokeEditor,
    onSuccess: async () => {
      setFailure(null);
      setNotice("Доступ редактора отозван досрочно.");
      await refresh();
    },
    onError: (error) => {
      setNotice(null);
      setFailure(errorMessage(error));
    },
  });
  const disableUser = useMutation({
    mutationFn: api.disableUser,
    onSuccess: async () => {
      setFailure(null);
      setNotice("Учётная запись заблокирована.");
      await refresh();
    },
    onError: (error) => {
      setNotice(null);
      setFailure(errorMessage(error));
    },
  });

  const busy =
    createEditor.isPending ||
    grantEditor.isPending ||
    revokeEditor.isPending ||
    disableUser.isPending;

  const submitEditor = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    const editorExpiresAt = toIso(newEditorExpiry);
    if (editorExpiresAt === null || new Date(editorExpiresAt) <= new Date()) {
      setNotice(null);
      setFailure("Укажите будущую дату окончания доступа.");
      return;
    }
    createEditor.mutate({
      login,
      display_name: displayName,
      password,
      editor_expires_at: editorExpiresAt,
    });
  };

  const grant = (user: ManagedUser) => {
    const localExpiry = grantExpiry[user.id] ?? localDateTimeAfter(7);
    const expiresAt = toIso(localExpiry);
    if (expiresAt === null || new Date(expiresAt) <= new Date()) {
      setNotice(null);
      setFailure("Укажите будущую дату окончания доступа.");
      return;
    }
    grantEditor.mutate({ userId: user.id, expiresAt });
  };

  if (users.isPending) {
    return <LoadingState label="Загружаем пользователей…" />;
  }
  if (users.isError) {
    return (
      <ErrorState
        title="Пользователи недоступны"
        message="Сервер не вернул список учётных записей."
        onRetry={() => void users.refetch()}
      />
    );
  }

  return (
    <section>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Администрирование доступа</p>
          <h2>Пользователи и временные редакторы</h2>
        </div>
        <span className="user-count">Учётных записей: {users.data.total}</span>
      </div>
      <p className="lede">
        Редактор получает доступ только до указанной даты. Назначение администратора на этом
        экране недоступно и выполняется отдельным защищённым действием.
      </p>

      {failure === null ? null : <p className="management-message management-message--error" role="alert">{failure}</p>}
      {notice === null ? null : <p className="management-message management-message--success" role="status">{notice}</p>}

      <form className="editor-form temporary-editor-form" onSubmit={submitEditor}>
        <fieldset>
          <legend>Создать временного редактора</legend>
          <div className="form-grid">
            <label>
              Логин
              <input
                autoComplete="off"
                maxLength={100}
                minLength={3}
                onChange={(event) => { setLogin(event.target.value); }}
                required
                value={login}
              />
            </label>
            <label>
              Отображаемое имя
              <input
                autoComplete="name"
                maxLength={160}
                onChange={(event) => { setDisplayName(event.target.value); }}
                required
                value={displayName}
              />
            </label>
            <label>
              Временный пароль
              <input
                autoComplete="new-password"
                maxLength={128}
                minLength={12}
                onChange={(event) => { setPassword(event.target.value); }}
                required
                type="password"
                value={password}
              />
            </label>
            <label>
              Доступ редактора до
              <input
                min={localDateTimeAfter(0)}
                onChange={(event) => { setNewEditorExpiry(event.target.value); }}
                required
                type="datetime-local"
                value={newEditorExpiry}
              />
            </label>
          </div>
          <p className="field-help">
            После окончания срока пользователь сохранит безопасный студенческий доступ.
          </p>
          <button className="button button--primary" disabled={busy} type="submit">
            {createEditor.isPending ? "Создаём…" : "Создать редактора"}
          </button>
        </fieldset>
      </form>

      <div className="managed-users" aria-label="Список пользователей">
        {users.data.items.map((managedUser) => {
          const isAdministrator = managedUser.roles.includes("administrator");
          const isEditor = managedUser.roles.includes("editor");
          const isDisabled = managedUser.status === "disabled";
          const expired =
            managedUser.editor_expires_at !== null &&
            new Date(managedUser.editor_expires_at) <= new Date() &&
            !isEditor;
          const localExpiry = grantExpiry[managedUser.id] ?? localDateTimeAfter(7);
          return (
            <article className="managed-user-card" key={managedUser.id}>
              <div className="managed-user-card__identity">
                <span className="account__avatar" aria-hidden="true">
                  {managedUser.display_name.slice(0, 2).toUpperCase()}
                </span>
                <span>
                  <strong>{managedUser.display_name}</strong>
                  <small>@{managedUser.login}</small>
                </span>
              </div>
              <div className="managed-user-card__state">
                <span className={`status-badge status-badge--${isDisabled ? "failed" : isEditor ? "published" : "draft"}`}>
                  {isDisabled ? "Заблокирован" : accessLabel(managedUser)}
                </span>
                {managedUser.editor_expires_at === null ? null : (
                  <small>
                    {expired ? "Доступ истёк: " : "Редактор до: "}
                    <time dateTime={managedUser.editor_expires_at}>
                      {formatDate(managedUser.editor_expires_at)}
                    </time>
                  </small>
                )}
              </div>
              <div className="managed-user-card__actions">
                {isAdministrator ? (
                  <p>Администратор изменяется отдельным защищённым действием.</p>
                ) : isDisabled ? (
                  <p>Заблокированная учётная запись не получает доступ.</p>
                ) : (
                  <>
                    {isEditor ? (
                      <button
                        className="button button--quiet"
                        disabled={busy}
                        onClick={() => { revokeEditor.mutate(managedUser.id); }}
                        type="button"
                      >
                        Отозвать досрочно
                      </button>
                    ) : (
                      <label>
                        Доступ редактора до
                        <input
                          min={localDateTimeAfter(0)}
                          onChange={(event) => {
                            setGrantExpiry((current) => ({
                              ...current,
                              [managedUser.id]: event.target.value,
                            }));
                          }}
                          type="datetime-local"
                          value={localExpiry}
                        />
                        <button
                          className="button button--accent"
                          disabled={busy}
                          onClick={() => { grant(managedUser); }}
                          type="button"
                        >
                          {expired ? "Назначить снова" : "Назначить редактором"}
                        </button>
                      </label>
                    )}
                    <button
                      className="button button--danger"
                      disabled={busy}
                      onClick={() => {
                        if (window.confirm(`Заблокировать пользователя «${managedUser.display_name}»?`)) {
                          disableUser.mutate(managedUser.id);
                        }
                      }}
                      type="button"
                    >
                      Заблокировать
                    </button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
