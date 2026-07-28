import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { api } from "../api/client";
import type { AuditEvent } from "../api/contracts";
import { userErrorMessage } from "../api/errors";
import { useAuditEvents } from "../audit/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";

const PAGE_SIZE = 50;

const ACTION_LABELS: Readonly<Record<string, string>> = {
  "auth.logout": "Выход из системы",
  "identity.initial_administrator_created": "Создан первый администратор",
  "identity.user_created": "Создан пользователь",
  "identity.editor_granted": "Назначена роль редактора",
  "identity.editor_expiry_changed": "Изменён срок роли редактора",
  "identity.editor_revoked": "Отозвана роль редактора",
  "identity.roles_changed": "Изменены роли пользователя",
  "identity.user_disabled": "Пользователь заблокирован",
  "component.created": "Создана карточка",
  "component.updated": "Изменена карточка",
  "component.media_attached": "К карточке прикреплён файл",
  "component.images_updated": "Изменены изображения карточки",
  "component.submitted_for_review": "Карточка отправлена на проверку",
  "component.changes_requested": "Карточка возвращена на исправление",
  "component.approved": "Карточка одобрена",
  "component.published": "Карточка опубликована",
  "component.hidden": "Карточка скрыта",
  "component.shown": "Карточка снова опубликована",
  "component.archived": "Карточка архивирована",
  "component.restored": "Карточка восстановлена",
  "component.merged": "Данные карточек объединены",
  "component.archived_by_merge": "Карточка архивирована после объединения",
  "import.job_submitted": "Запущена загрузка компонента",
  "import.job_retry_requested": "Запрошена повторная обработка компонента",
  "import.job_cancelled": "Загрузка компонента отменена",
  "import.job_enqueue_failed": "Запуск обработки компонента не удался",
  "import.submission_rejected": "Загрузка компонента отклонена",
  "media.job_retry_requested": "Запрошена повторная обработка файла",
  "media.job_enqueue_failed": "Запуск обработки файла не удался",
  "media.upload_reserved": "Начата загрузка файла",
  "media.upload_confirmed": "Загрузка файла подтверждена",
  "media.upload_rejected": "Загрузка файла отклонена",
  "media.processing_completed": "Обработка изображения завершена",
  "media.processing_failed": "Обработка изображения не удалась",
  "media.processing_rejected": "Изображение отклонено при обработке",
  "media.video_processing_completed": "Обработка видео завершена",
  "media.video_processing_failed": "Обработка видео не удалась",
  "media.video_processing_rejected": "Видео отклонено при обработке",
  "media.retention_asset_cleaned": "Файл окончательно удалён по сроку хранения",
  "media.retention_orphans_cleaned": "Удалены несвязанные файлы",
  "category.created": "Создана категория",
  "category.deactivated": "Категория отключена",
  "duplicate.merge": "Карточки объединены",
  "duplicate.attach": "Источник привязан к карточке",
  "duplicate.create": "Подтверждены разные карточки",
  "duplicate.reject": "Совпадение отклонено",
  "import_review.enrichment_relation_changed": "Изменена связь дополнения импорта",
  "import_review.identity_selected": "Выбрана карточка для импорта",
  "import_review.specification_mapped": "Сопоставлена характеристика импорта",
  "import_review.parser_issue_marked": "Отмечена проблема разбора",
  "import_review.draft_confirmed": "Проверка импорта подтверждена",
};

const OBJECT_LABELS: Readonly<Record<string, string>> = {
  session: "Сеанс",
  user: "Пользователь",
  component: "Карточка",
  category: "Категория",
  import_job: "Загрузка компонента",
  import_review_draft: "Черновик импорта",
  media_asset: "Файл",
  media_bucket: "Хранилище файлов",
  media_job: "Обработка файла",
  media_upload: "Загрузка файла",
  duplicate_candidate: "Проверка совпадения",
};

const OUTCOME_LABELS: Readonly<Record<string, string>> = {
  success: "Выполнено",
  failed: "Не выполнено",
  blocked: "Заблокировано",
  rejected: "Отклонено",
  error: "Ошибка",
};

function actionLabel(event: AuditEvent): string {
  if (event.action === "auth.login") {
    if (event.outcome === "success") return "Вход в систему";
    if (event.outcome === "blocked") return "Попытка входа заблокирована";
    return "Неудачная попытка входа";
  }
  if (event.action.startsWith("import_review.")) return "Изменена проверка импорта";
  if (event.action.startsWith("media.processing_")) return "Изменена обработка изображения";
  if (event.action.startsWith("media.video_processing_")) return "Изменена обработка видео";
  return ACTION_LABELS[event.action] ?? "Системное действие";
}

function filterActionLabel(action: string): string {
  if (action === "auth.login") return "Вход и неудачные попытки входа";
  if (action.startsWith("import_review.")) return "Изменение проверки импорта";
  if (action.startsWith("media.video_processing_")) return "Обработка видео";
  if (action.startsWith("media.processing_")) return "Обработка изображения";
  return ACTION_LABELS[action] ?? "Системное действие";
}

function actorLabel(event: AuditEvent): { name: string; detail: string | null } {
  if (event.actor.type === "system") return { name: "Система", detail: null };
  if (event.actor.id === null) {
    return { name: "Неавторизованный пользователь", detail: null };
  }
  return {
    name: event.actor.display_name ?? "Пользователь",
    detail: event.actor.login === null ? null : `@${event.actor.login}`,
  };
}

function objectLabel(event: AuditEvent): string {
  const type = OBJECT_LABELS[event.object.type] ?? "Объект";
  return event.object.id === null ? type : `${type} · ${event.object.id.slice(0, 8)}`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

function dateBoundary(value: string, nextDay: boolean): string | undefined {
  if (value === "") return undefined;
  const date = new Date(`${value}T00:00:00`);
  if (nextDay) date.setDate(date.getDate() + 1);
  return date.toISOString();
}

export function AuditLogPage() {
  const [userId, setUserId] = useState("");
  const [action, setAction] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [offset, setOffset] = useState(0);
  const filters = useMemo(
    () => ({
      userId: userId || undefined,
      action: action || undefined,
      occurredFrom: dateBoundary(dateFrom, false),
      occurredTo: dateBoundary(dateTo, true),
      limit: PAGE_SIZE,
      offset,
    }),
    [action, dateFrom, dateTo, offset, userId],
  );
  const events = useAuditEvents(filters);
  const users = useQuery({
    queryKey: ["administration", "users"],
    queryFn: api.listUsers,
    staleTime: 30_000,
  });

  if (events.isPending || users.isPending) {
    return <LoadingState label="Загружаем журнал действий…" />;
  }
  if (events.isError || users.isError) {
    return (
      <ErrorState
        title="Журнал действий недоступен"
        message={userErrorMessage(
          events.error ?? users.error,
          "Не удалось загрузить журнал. Попробуйте снова.",
        )}
        onRetry={() => {
          void Promise.all([events.refetch(), users.refetch()]);
        }}
      />
    );
  }

  const hasFilters = userId !== "" || action !== "" || dateFrom !== "" || dateTo !== "";
  const actions = [...events.data.available_actions].sort((left, right) =>
    filterActionLabel(left).localeCompare(filterActionLabel(right), "ru"));

  return (
    <section className="audit-page">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Только для уполномоченного администратора</p>
          <h2>Журнал действий</h2>
        </div>
        <span>Событий: {events.data.total}</span>
      </div>
      <p className="lede">
        Журнал доступен только для чтения. Он фиксирует важные действия без паролей,
        токенов и других секретов.
      </p>

      <div className="audit-filters" aria-label="Фильтры журнала">
        <label>
          Пользователь
          <select
            value={userId}
            onChange={(event) => {
              setUserId(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">Все пользователи</option>
            {users.data.items.map((user) => (
              <option key={user.id} value={user.id}>{user.display_name} (@{user.login})</option>
            ))}
          </select>
        </label>
        <label>
          Действие
          <select
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">Все действия</option>
            {actions.map((value) => (
              <option key={value} value={value}>{filterActionLabel(value)}</option>
            ))}
          </select>
        </label>
        <label>
          Дата с
          <input
            type="date"
            value={dateFrom}
            onChange={(event) => {
              setDateFrom(event.target.value);
              setOffset(0);
            }}
          />
        </label>
        <label>
          Дата по
          <input
            min={dateFrom || undefined}
            type="date"
            value={dateTo}
            onChange={(event) => {
              setDateTo(event.target.value);
              setOffset(0);
            }}
          />
        </label>
        <button
          className="button button--quiet"
          disabled={!hasFilters}
          type="button"
          onClick={() => {
            setUserId("");
            setAction("");
            setDateFrom("");
            setDateTo("");
            setOffset(0);
          }}
        >
          Сбросить фильтры
        </button>
      </div>

      {events.data.items.length === 0 ? (
        <SplatEmptyState
          icon="◇"
          title={hasFilters ? "События не найдены" : "Журнал пока пуст"}
          description={
            hasFilters
              ? "Измените пользователя, действие или диапазон дат."
              : "Важные действия появятся здесь после их выполнения."
          }
        />
      ) : (
        <div className="audit-list" role="list">
          {events.data.items.map((event) => {
            const actor = actorLabel(event);
            return (
              <article className="audit-row" key={event.id} role="listitem">
                <time dateTime={event.occurred_at}>{formatDate(event.occurred_at)}</time>
                <span><strong>{actor.name}</strong>{actor.detail === null ? null : <small>{actor.detail}</small>}</span>
                <span><strong>{actionLabel(event)}</strong><small>{objectLabel(event)}</small></span>
                <span className={`status-badge status-badge--${event.outcome === "success" ? "succeeded" : "failed"}`}>
                  {OUTCOME_LABELS[event.outcome] ?? "Зафиксировано"}
                </span>
              </article>
            );
          })}
        </div>
      )}

      {events.data.total <= PAGE_SIZE ? null : (
        <nav className="pagination" aria-label="Страницы журнала">
          <button
            className="button button--quiet"
            disabled={offset === 0}
            type="button"
            onClick={() => { setOffset(Math.max(0, offset - PAGE_SIZE)); }}
          >
            Назад
          </button>
          <span>События {offset + 1}–{Math.min(offset + PAGE_SIZE, events.data.total)}</span>
          <button
            className="button button--quiet"
            disabled={offset + PAGE_SIZE >= events.data.total}
            type="button"
            onClick={() => { setOffset(offset + PAGE_SIZE); }}
          >
            Далее
          </button>
        </nav>
      )}
    </section>
  );
}
