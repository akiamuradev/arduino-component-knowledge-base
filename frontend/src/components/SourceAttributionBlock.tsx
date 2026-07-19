import type { SourceSnapshot } from "../api/contracts";

function safeUrl(value: string | null): string | null {
  if (value === null) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("ru-RU", {
        day: "2-digit",
        month: "long",
        year: "numeric",
      }).format(date);
}

function revisionLabel(source: SourceSnapshot): string {
  const commit = source.source_revision.slice(0, 12);
  return source.source_tag === null ? commit : `${source.source_tag} · ${commit}`;
}

function Snapshot({ source }: { source: SourceSnapshot }) {
  const originalUrl = safeUrl(source.original_url);
  const repositoryUrl = safeUrl(source.repository_url);
  const licenseUrl = safeUrl(source.license_url);
  return (
    <li className="source-attribution__snapshot">
      <h3>{source.display_name}</h3>
      <dl className="source-facts">
        <div><dt>Лицензия</dt><dd>{source.license_name} · {source.license_spdx}</dd></div>
        <div><dt>Revision</dt><dd><code>{revisionLabel(source)}</code></dd></div>
        {source.source_file_path === null ? null : <div><dt>Файл</dt><dd><code>{source.source_file_path}</code></dd></div>}
        {source.source_entry_name === null ? null : <div><dt>Entry</dt><dd>{source.source_entry_name}</dd></div>}
        <div><dt>Parser</dt><dd>{source.parser_name} {source.parser_version}</dd></div>
        <div><dt>Импортировано</dt><dd>{formatDate(source.imported_at)}</dd></div>
      </dl>
      <p><strong>Attribution:</strong> {source.attribution}</p>
      <p><strong>Изменения:</strong> {source.modifications_notice}</p>
      <div className="inline-actions">
        {originalUrl === null ? null : <a href={originalUrl} target="_blank" rel="noopener noreferrer">Открыть источник ↗</a>}
        {repositoryUrl === null ? null : <a href={repositoryUrl} target="_blank" rel="noopener noreferrer">Repository ↗</a>}
        {licenseUrl === null ? null : <a href={licenseUrl} target="_blank" rel="noopener noreferrer">Лицензия ↗</a>}
      </div>
    </li>
  );
}

export function SourceAttributionBlock({ sources }: { sources: SourceSnapshot[] }) {
  if (sources.length === 0) return null;
  return (
    <section className="source-attribution" aria-labelledby="source-attribution-title">
      <p className="section-kicker">Происхождение и лицензирование</p>
      <h2 id="source-attribution-title">{sources.length === 1 ? "Источник материала" : "Источники материала"}</h2>
      <p>Эти сведения сохранены backend вместе с revision карточки и доступны только для чтения.</p>
      <ul>{sources.map((source) => <Snapshot key={`${source.repository_url ?? source.display_name}:${source.source_revision}:${source.source_file_path ?? ""}:${source.source_entry_name ?? ""}`} source={source} />)}</ul>
    </section>
  );
}
