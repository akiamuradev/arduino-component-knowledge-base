import { type SyntheticEvent, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import type {
  ImportDisplayStatus,
  ImportJob,
  RepositoryEntry,
  RepositoryImportInput,
  RepositoryPreview,
  RepositorySourceKey,
} from "../api/contracts";
import { hasPermission } from "../auth/permissions";
import { useCurrentUser } from "../auth/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";
import {
  useCancelImport,
  useCreateRepositoryImport,
  useImportJob,
  useImports,
  useRepositoryEntryDiscovery,
  useRepositoryFileDiscovery,
  useRepositoryPreview,
  useRetryImport,
} from "../imports/queries";

const sourceOptions: {
  key: RepositorySourceKey;
  label: string;
  revision: string;
  help: string;
}[] = [
  {
    key: "seeed_wiki",
    label: "База знаний Seeed Studio",
    revision: "docusaurus-version",
    help: "Документация модулей, датчиков и плат Seeed Studio.",
  },
  {
    key: "kicad_symbols",
    label: "Официальные библиотеки KiCad",
    revision: "9.0.9.1",
    help: "Обозначения электронных компонентов из официальной библиотеки KiCad.",
  },
];

const statusLabels: Record<ImportDisplayStatus, string> = {
  pending: "Ожидает обработки",
  processing: "Обрабатывается",
  needs_review: "Требует проверки",
  ready: "Готово",
  published: "Опубликовано",
  error: "Ошибка обработки",
  cancelled: "Отменено",
};

function errorMessage(error: unknown): string | null {
  if (error === null || error === undefined) return null;
  if (error instanceof ApiError && error.status === 403) {
    return "У вас недостаточно прав для этого действия.";
  }
  if (error instanceof ApiError && error.status === 409) {
    return "Состояние загрузки уже изменилось. Обновите список и повторите действие.";
  }
  return "Не удалось выполнить действие. Повторите попытку позже.";
}

function stringField(preview: RepositoryPreview, ...keys: string[]): string | null {
  for (const key of keys) {
    const value = preview.normalized_fields[key];
    if (typeof value === "string" && value.trim() !== "") return value;
  }
  return null;
}

function arrayLength(preview: RepositoryPreview, key: string): number | null {
  const value = preview.normalized_fields[key];
  return Array.isArray(value) ? value.length : null;
}

function safeExternalUrl(value: string): string | null {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function currentStatus(job: ImportJob): ImportDisplayStatus {
  if (job.status === "queued" || job.status === "retrying") return "pending";
  if (job.status === "running") return "processing";
  if (job.status === "failed") return "error";
  if (job.status === "cancelled") return "cancelled";
  return job.parse_status === "parsed_with_warnings" ? "needs_review" : "ready";
}

function PreviewPanel({ preview }: { preview: RepositoryPreview }) {
  const title = stringField(preview, "title", "symbol_name") ?? "Без названия";
  const summary = stringField(preview, "summary", "description") ?? "Описание не найдено.";
  const pins = arrayLength(preview, "pins");
  const specifications = arrayLength(preview, "specifications");
  const originalUrl = safeExternalUrl(preview.original_url);
  const licenseUrl = safeExternalUrl(preview.license.url);
  const needsReview = preview.parse_status === "parsed_with_warnings";
  return (
    <section className="import-preview" aria-labelledby="import-preview-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Предварительный просмотр</p>
          <h3 id="import-preview-title">{title}</h3>
        </div>
        <span className={`status-badge status-badge--${needsReview ? "needs-review" : "ready"}`}>
          {needsReview ? "Требует проверки" : "Готово к загрузке"}
        </span>
      </div>
      <p className="preview-summary">{summary}</p>
      <dl className="source-facts">
        <div><dt>Источник</dt><dd>{sourceOptions.find((item) => item.key === preview.source_key)?.label}</dd></div>
        <div><dt>Версия материалов</dt><dd>{preview.requested_revision}</dd></div>
        <div><dt>Исходный документ</dt><dd>{preview.file_path}</dd></div>
        {preview.entry_name === null ? null : <div><dt>Компонент</dt><dd>{preview.entry_name}</dd></div>}
        {pins === null ? null : <div><dt>Выводы</dt><dd>{pins}</dd></div>}
        {specifications === null ? null : <div><dt>Характеристики</dt><dd>{specifications}</dd></div>}
      </dl>
      <section className="license-panel">
        <p className="section-kicker">Лицензия и авторство</p>
        <h4>{preview.license.name}</h4>
        <p><strong>{preview.license.spdx}</strong> · {preview.license.attribution}</p>
        <p>{preview.modifications_notice}</p>
        <div className="inline-actions">
          {originalUrl === null ? null : <a href={originalUrl} target="_blank" rel="noopener noreferrer">Открыть источник ↗</a>}
          {licenseUrl === null ? null : <a href={licenseUrl} target="_blank" rel="noopener noreferrer">Открыть лицензию ↗</a>}
        </div>
      </section>
      {preview.warnings.length === 0 ? null : (
        <div className="warning-list" role="status">
          <strong>Потребуется дополнительная проверка</strong>
          <p>В исходных данных найдены неоднозначные сведения: {preview.warnings.length}.</p>
        </div>
      )}
    </section>
  );
}

export function AdminImportPage() {
  const currentUser = useCurrentUser();
  const [showForm, setShowForm] = useState(false);
  const [sourceKey, setSourceKey] = useState<RepositorySourceKey>("seeed_wiki");
  const [revision, setRevision] = useState("docusaurus-version");
  const [query, setQuery] = useState("Grove Button");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [entryQuery, setEntryQuery] = useState("");
  const [selectedEntry, setSelectedEntry] = useState<RepositoryEntry | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const imports = useImports();
  const retryImport = useRetryImport();
  const cancelImport = useCancelImport();
  const files = useRepositoryFileDiscovery();
  const entries = useRepositoryEntryDiscovery();
  const preview = useRepositoryPreview();
  const createImport = useCreateRepositoryImport();
  const job = useImportJob(jobId);
  const source = sourceOptions.find((item) => item.key === sourceKey);
  const canDiagnose = currentUser.data !== undefined
    && hasPermission(currentUser.data, "system.diagnostics");

  const resetResult = () => {
    setSelectedFile(null);
    setSelectedEntry(null);
    setJobId(null);
    entries.reset();
    preview.reset();
    createImport.reset();
  };
  const input = (): RepositoryImportInput | null => {
    if (selectedFile === null) return null;
    if (sourceKey === "kicad_symbols" && selectedEntry?.entry_name == null) return null;
    return {
      source_key: sourceKey,
      revision,
      file_path: selectedFile,
      entry_name: sourceKey === "kicad_symbols" ? selectedEntry?.entry_name ?? null : null,
    };
  };
  const discover = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    resetResult();
    files.mutate({ sourceKey, revision, query, limit: 25 });
  };
  const chooseFile = (filePath: string) => {
    setSelectedFile(filePath);
    setSelectedEntry(null);
    setJobId(null);
    preview.reset();
    createImport.reset();
    entries.mutate({ sourceKey, revision, filePath, limit: sourceKey === "seeed_wiki" ? 1 : 50 });
  };
  const discoverEntries = (event: SyntheticEvent<HTMLFormElement, SubmitEvent>) => {
    event.preventDefault();
    if (selectedFile === null) return;
    setSelectedEntry(null);
    preview.reset();
    entries.mutate({ sourceKey, revision, filePath: selectedFile, query: entryQuery, limit: 50 });
  };
  const previewInput = input();
  const canCreate = preview.data !== undefined
    && ["parsed", "parsed_with_warnings"].includes(preview.data.parse_status)
    && previewInput !== null;
  const requestError = errorMessage(
    files.error
      ?? entries.error
      ?? preview.error
      ?? createImport.error
      ?? job.error
      ?? retryImport.error
      ?? cancelImport.error,
  );

  return (
    <section className="admin-import-page">
      <div className="section-heading import-page-heading">
        <div>
          <p className="eyebrow">Рабочая область редактора</p>
          <h2>Загрузка компонентов</h2>
        </div>
        <div className="inline-actions">
          {canDiagnose ? <Link className="button button--quiet" to="/admin/jobs">Диагностика</Link> : null}
          <button
            className="button button--primary"
            type="button"
            aria-expanded={showForm}
            aria-controls="add-component"
            onClick={() => {
              setShowForm((value) => !value);
            }}
          >
            {showForm ? "Закрыть форму" : "Добавить компонент"}
          </button>
        </div>
      </div>
      <p className="lede">
        Добавляйте компоненты из разрешённых источников и следите за результатом обработки.
        Новые карточки сохраняются как черновики и публикуются только после проверки.
      </p>
      {requestError === null ? null : (
        <p className="form-error" role="alert">{requestError}</p>
      )}

      <section className="import-list-section" aria-labelledby="import-list-title">
        <div className="section-heading section-heading--compact">
          <div><p className="section-kicker">Последние операции</p><h3 id="import-list-title">Список загрузок</h3></div>
          <span className="user-count">{imports.data?.total ?? 0}</span>
        </div>
        {imports.isPending ? <LoadingState label="Загружаем список компонентов…" /> : null}
        {imports.isError ? (
          <ErrorState
            title="Список загрузок недоступен"
            message="Не удалось получить актуальные данные."
            onRetry={() => {
              void imports.refetch();
            }}
          />
        ) : null}
        {imports.data?.items.length === 0 ? (
          <SplatEmptyState
            icon="⇣"
            title="Загрузок пока нет"
            description="Нажмите «Добавить компонент», чтобы создать первую."
          />
        ) : null}
        {imports.data === undefined || imports.data.items.length === 0 ? null : (
          <div className="import-list" role="table" aria-label="Загрузки компонентов">
            <div className="import-list__head" role="row">
              <span role="columnheader">Название</span>
              <span role="columnheader">Источник</span>
              <span role="columnheader">Кто добавил</span>
              <span role="columnheader">Дата</span>
              <span role="columnheader">Состояние</span>
              <span role="columnheader">Результат</span>
              <span role="columnheader">Действия</span>
            </div>
            {imports.data.items.map((item) => (
              <article className="import-list__row" role="row" key={item.id}>
                <strong role="cell">{item.title}</strong>
                <span role="cell">{item.source}</span>
                <span role="cell">{item.requested_by}</span>
                <time role="cell" dateTime={item.created_at}>{formatDate(item.created_at)}</time>
                <span role="cell">
                  <span className={`status-badge status-badge--${item.status}`}>
                    {statusLabels[item.status]}
                  </span>
                </span>
                <span role="cell">{item.result}</span>
                <span className="import-list__actions" role="cell">
                  {item.component_id === null ? null : (
                    <Link className="button button--quiet" to={`/admin/components/${item.component_id}/edit`}>
                      Открыть карточку
                    </Link>
                  )}
                  {item.can_retry ? (
                    <button
                      className="button button--quiet"
                      disabled={retryImport.isPending}
                      type="button"
                      onClick={() => {
                        retryImport.mutate(item.id);
                      }}
                    >
                      Повторить
                    </button>
                  ) : null}
                  {item.can_cancel ? (
                    <button
                      className="button button--danger"
                      disabled={cancelImport.isPending}
                      type="button"
                      onClick={() => {
                        cancelImport.mutate(item.id);
                      }}
                    >
                      Отменить
                    </button>
                  ) : null}
                  {item.component_id === null && !item.can_retry && !item.can_cancel ? "—" : null}
                </span>
              </article>
            ))}
          </div>
        )}
      </section>

      {showForm ? (
        <section className="import-create-panel" id="add-component">
          <div>
            <p className="section-kicker">Новая загрузка</p>
            <h3>Добавить компонент</h3>
            <p>Выберите источник и найдите нужный компонент перед созданием черновика.</p>
          </div>
          <form className="import-controls" onSubmit={discover}>
            <label>Источник<select value={sourceKey} onChange={(event) => {
              const next = event.target.value as RepositorySourceKey;
              const option = sourceOptions.find((item) => item.key === next);
              setSourceKey(next);
              setRevision(option?.revision ?? "docusaurus-version");
              setQuery(next === "seeed_wiki" ? "Grove Button" : "Sensor Temperature");
              resetResult();
            }}>{sourceOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
            <label>Версия материалов<input required maxLength={100} value={revision} onChange={(event) => { setRevision(event.target.value); resetResult(); }} /></label>
            <label>Поиск компонента<input required minLength={2} maxLength={100} value={query} onChange={(event) => { setQuery(event.target.value); }} /></label>
            <button className="button button--primary" disabled={files.isPending} type="submit">{files.isPending ? "Ищем…" : "Найти"}</button>
          </form>
          <p className="field-help">{source?.help ?? "Источник недоступен."}</p>
          {files.data === undefined ? null : (
            <section className="discovery-results">
              <div className="section-heading"><div><p className="section-kicker">Результаты поиска</p><h3>Найденные материалы</h3></div><span>{files.data.files.length}</span></div>
              {files.data.files.length === 0 ? <p>Совпадений нет. Измените запрос или версию материалов.</p> : <div className="selection-list">{files.data.files.map((file) => <button className={selectedFile === file.file_path ? "selected" : ""} key={file.file_path} type="button" onClick={() => { chooseFile(file.file_path); }}><strong>{file.file_path.split("/").at(-1)}</strong><small>{file.file_path}</small></button>)}</div>}
            </section>
          )}
          {sourceKey !== "kicad_symbols" || selectedFile === null ? null : <form className="entry-search" onSubmit={discoverEntries}><label>Поиск обозначения<input maxLength={100} value={entryQuery} placeholder="Например, LM35" onChange={(event) => { setEntryQuery(event.target.value); }} /></label><button className="button button--quiet" disabled={entries.isPending} type="submit">Найти обозначения</button></form>}
          {entries.data === undefined ? null : <section className="discovery-results"><h3>{sourceKey === "seeed_wiki" ? "Документ" : "Компоненты"}</h3><div className="selection-list">{entries.data.entries.map((entry) => <button className={selectedEntry !== null && selectedEntry.entry_name === entry.entry_name && selectedEntry.file_path === entry.file_path ? "selected" : ""} key={`${entry.file_path}:${entry.entry_name ?? "document"}`} type="button" onClick={() => { setSelectedEntry(entry); preview.reset(); setJobId(null); }}><strong>{entry.title ?? entry.entry_name ?? entry.file_path}</strong><small>{entry.entry_name ?? "Документ"}</small></button>)}</div></section>}
          <div className="editor-actions">
            <button className="button button--accent" disabled={previewInput === null || preview.isPending} type="button" onClick={() => { if (previewInput !== null) preview.mutate(previewInput); }}>{preview.isPending ? "Готовим просмотр…" : "Предварительный просмотр"}</button>
            <button className="button button--success" disabled={!canCreate || createImport.isPending} type="button" onClick={() => { if (previewInput !== null) createImport.mutate({ input: previewInput, idempotencyKey: crypto.randomUUID() }, { onSuccess: (created) => { setJobId(created.id); } }); }}>{createImport.isPending ? "Добавляем…" : "Начать загрузку"}</button>
          </div>
          {preview.data === undefined ? null : <PreviewPanel preview={preview.data} />}
          {jobId === null ? null : (
            <section className="import-job-status" aria-live="polite">
              <p className="section-kicker">Текущая загрузка</p>
              {job.isPending ? <h3>Получаем состояние…</h3> : job.isError ? <h3>Состояние временно недоступно</h3> : (
                <>
                  <h3>{statusLabels[currentStatus(job.data)]}</h3>
                  <p>{currentStatus(job.data) === "error" ? "Не удалось обработать компонент. Повторите действие из списка загрузок." : "Состояние обновится автоматически."}</p>
                  {job.data.draft_component_id === null ? null : (
                    <Link className="button button--primary" to={`/admin/components/${job.data.draft_component_id}/edit`}>
                      Открыть карточку
                    </Link>
                  )}
                </>
              )}
            </section>
          )}
        </section>
      ) : null}
    </section>
  );
}
