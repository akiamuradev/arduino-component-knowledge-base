import { type SyntheticEvent, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import type {
  RepositoryEntry,
  RepositoryImportInput,
  RepositoryPreview,
  RepositorySourceKey,
} from "../api/contracts";
import { ErrorState } from "../components/AsyncStates";
import {
  useCreateRepositoryImport,
  useImportJob,
  useRepositoryEntryDiscovery,
  useRepositoryFileDiscovery,
  useRepositoryPreview,
} from "../imports/queries";

const sourceOptions: {
  key: RepositorySourceKey;
  label: string;
  revision: string;
  help: string;
}[] = [
  {
    key: "seeed_wiki",
    label: "Seeed Studio Wiki",
    revision: "docusaurus-version",
    help: "Документация модулей, датчиков и плат. Поиск ограничен sites/en/docs.",
  },
  {
    key: "kicad_symbols",
    label: "Official KiCad Libraries",
    revision: "9.0.9.1",
    help: "Официальные библиотеки символов KiCad 9.x. Сначала выберите library, затем symbol.",
  },
];

function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : error instanceof Error ? error.message : null;
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

function PreviewPanel({ preview }: { preview: RepositoryPreview }) {
  const title = stringField(preview, "title", "symbol_name") ?? "Без названия";
  const summary = stringField(preview, "summary", "description") ?? "Описание не извлечено.";
  const pins = arrayLength(preview, "pins");
  const specifications = arrayLength(preview, "specifications");
  const originalUrl = safeExternalUrl(preview.original_url);
  const licenseUrl = safeExternalUrl(preview.license.url);
  return (
    <section className="import-preview" aria-labelledby="import-preview-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Preview до создания draft</p>
          <h3 id="import-preview-title">{title}</h3>
        </div>
        <span className={`status-badge status-badge--${preview.parse_status}`}>
          {preview.parse_status}
        </span>
      </div>
      <p className="preview-summary">{summary}</p>
      <dl className="source-facts">
        <div><dt>Repository</dt><dd>{preview.repository_url}</dd></div>
        <div><dt>Commit SHA</dt><dd><code>{preview.revision}</code></dd></div>
        <div><dt>Исходный файл</dt><dd><code>{preview.file_path}</code></dd></div>
        {preview.entry_name === null ? null : <div><dt>Source entry</dt><dd>{preview.entry_name}</dd></div>}
        <div><dt>Parser</dt><dd>{preview.parser_name} {preview.parser_version}</dd></div>
        {pins === null ? null : <div><dt>Pins</dt><dd>{pins}</dd></div>}
        {specifications === null ? null : <div><dt>Характеристики</dt><dd>{specifications}</dd></div>}
      </dl>
      <section className="license-panel">
        <p className="section-kicker">Лицензия и attribution</p>
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
          <strong>Нужна ручная проверка</strong>
          <ul>{preview.warnings.map((warning) => <li key={warning}><code>{warning}</code></li>)}</ul>
        </div>
      )}
      <details>
        <summary>Provenance отдельных полей</summary>
        <dl className="provenance-list">
          {Object.entries(preview.provenance).map(([field, values]) => (
            <div key={field}><dt>{field}</dt><dd>{values.map((item) => `${item.confidence}: ${item.transformation}`).join(", ")}</dd></div>
          ))}
        </dl>
      </details>
    </section>
  );
}

export function AdminImportPage() {
  const [sourceKey, setSourceKey] = useState<RepositorySourceKey>("seeed_wiki");
  const [revision, setRevision] = useState("docusaurus-version");
  const [query, setQuery] = useState("Grove Button");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [entryQuery, setEntryQuery] = useState("");
  const [selectedEntry, setSelectedEntry] = useState<RepositoryEntry | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const files = useRepositoryFileDiscovery();
  const entries = useRepositoryEntryDiscovery();
  const preview = useRepositoryPreview();
  const createImport = useCreateRepositoryImport();
  const job = useImportJob(jobId);
  const source = sourceOptions.find((item) => item.key === sourceKey);

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
  const requestError = errorCode(files.error ?? entries.error ?? preview.error ?? createImport.error ?? job.error);
  const jobSourceUrl = job.data === undefined ? null : safeExternalUrl(job.data.canonical_url ?? "");

  return (
    <section className="admin-import-page">
      <div className="section-heading">
        <div><p className="eyebrow">Только administrator</p><h2>Импорт из Git-источника</h2></div>
        <Link className="button button--quiet" to="/admin/jobs">Фоновые задачи</Link>
      </div>
      <p className="lede">Источник и revision проверяются backend. Импорт создаёт только draft; публикация выполняется отдельно после ручной проверки.</p>
      <form className="import-controls" onSubmit={discover}>
        <label>Источник<select value={sourceKey} onChange={(event) => {
          const next = event.target.value as RepositorySourceKey;
          const option = sourceOptions.find((item) => item.key === next);
          setSourceKey(next); setRevision(option?.revision ?? "docusaurus-version"); setQuery(next === "seeed_wiki" ? "Grove Button" : "Sensor Temperature"); resetResult();
        }}>{sourceOptions.map((option) => <option key={option.key} value={option.key}>{option.label}</option>)}</select></label>
        <label>Revision<input required maxLength={100} value={revision} onChange={(event) => { setRevision(event.target.value); resetResult(); }} /></label>
        <label>Поиск документа или library<input required minLength={2} maxLength={100} value={query} onChange={(event) => { setQuery(event.target.value); }} /></label>
        <button className="button button--primary" disabled={files.isPending} type="submit">{files.isPending ? "Ищем…" : "Найти"}</button>
      </form>
      <p className="field-help">{source?.help ?? "Источник не поддерживается."}</p>
      {requestError === null ? null : <ErrorState title="Операция не выполнена" message={`Backend error: ${requestError}`} />}
      {files.data === undefined ? null : (
        <section className="discovery-results">
          <div className="section-heading"><div><p className="section-kicker">Bounded discovery</p><h3>Найденные файлы</h3></div><span>{files.data.files.length} из {files.data.files_scanned}</span></div>
          {files.data.files.length === 0 ? <p>Совпадений нет. Измените запрос или revision.</p> : <div className="selection-list">{files.data.files.map((file) => <button className={selectedFile === file.file_path ? "selected" : ""} key={file.file_path} type="button" onClick={() => { chooseFile(file.file_path); }}><strong>{file.file_path.split("/").at(-1)}</strong><small>{file.file_path}</small><span>{file.size === null ? "размер не передан" : `${String(file.size)} bytes`}</span></button>)}</div>}
        </section>
      )}
      {sourceKey !== "kicad_symbols" || selectedFile === null ? null : <form className="entry-search" onSubmit={discoverEntries}><label>Поиск symbol<input maxLength={100} value={entryQuery} placeholder="Например, LM35" onChange={(event) => { setEntryQuery(event.target.value); }} /></label><button className="button button--quiet" disabled={entries.isPending} type="submit">Найти symbols</button></form>}
      {entries.data === undefined ? null : <section className="discovery-results"><h3>{sourceKey === "seeed_wiki" ? "Документ" : "Symbols"}</h3><div className="selection-list">{entries.data.entries.map((entry) => <button className={selectedEntry !== null && selectedEntry.entry_name === entry.entry_name && selectedEntry.file_path === entry.file_path ? "selected" : ""} key={`${entry.file_path}:${entry.entry_name ?? "document"}`} type="button" onClick={() => { setSelectedEntry(entry); preview.reset(); setJobId(null); }}><strong>{entry.title ?? entry.entry_name ?? entry.file_path}</strong><small>{entry.entry_name ?? "Markdown document"}</small></button>)}</div></section>}
      <div className="editor-actions">
        <button className="button button--accent" disabled={previewInput === null || preview.isPending} type="button" onClick={() => { if (previewInput !== null) preview.mutate(previewInput); }}>{preview.isPending ? "Готовим preview…" : "Показать preview"}</button>
        <button className="button button--success" disabled={!canCreate || createImport.isPending} type="button" onClick={() => { if (previewInput !== null) createImport.mutate({ input: previewInput, idempotencyKey: crypto.randomUUID() }, { onSuccess: (created) => { setJobId(created.id); } }); }}>{createImport.isPending ? "Создаём job…" : "Создать черновик"}</button>
      </div>
      {preview.data === undefined ? null : <PreviewPanel preview={preview.data} />}
      {jobId === null ? null : <section className="import-job-status" aria-live="polite"><p className="section-kicker">Import job</p>{job.isPending ? <h3>Задача поставлена в очередь…</h3> : job.isError ? <h3>Статус job недоступен</h3> : <><h3>{job.data.status}</h3><dl className="source-facts"><div><dt>Job</dt><dd><code>{job.data.id}</code></dd></div><div><dt>Попытки</dt><dd>{job.data.attempts}/{job.data.max_attempts}</dd></div><div><dt>Parse status</dt><dd>{job.data.parse_status ?? "ожидание"}</dd></div></dl>{job.data.warnings_json.length === 0 ? null : <div className="warning-list"><strong>Предупреждения parser</strong><ul>{job.data.warnings_json.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}{job.data.status === "failed" ? <p className="form-error" role="alert">Backend error: {job.data.error_code ?? "import_failed"}</p> : null}{job.data.draft_component_id === null ? null : <div className="inline-actions"><Link className="button button--primary" to={`/admin/components/${job.data.draft_component_id}/edit`}>Открыть draft</Link>{jobSourceUrl === null ? null : <a href={jobSourceUrl} target="_blank" rel="noopener noreferrer">Открыть источник ↗</a>}</div>}</>}</section>}
    </section>
  );
}
