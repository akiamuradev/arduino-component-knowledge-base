import { useQuery } from "@tanstack/react-query";

import type { CatalogSource } from "../api/contracts";
import { catalogSourcesQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";

function safeUrl(value: string | null): string | null {
  if (value === null) return null;
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

function SourceCard({ source }: { source: CatalogSource }) {
  const repositoryUrl = safeUrl(source.repository_url);
  const licenseUrl = safeUrl(source.license_url);
  return (
    <article className="source-card">
      <div className="section-heading"><div><p className="section-kicker">{source.source_type}</p><h2>{source.display_name}</h2></div><span className={`status-badge status-badge--${source.status}`}>{source.status}</span></div>
      <dl className="source-facts">
        <div><dt>Назначение</dt><dd>{source.content_policy}</dd></div>
        <div><dt>Лицензия</dt><dd>{source.license_name ?? "Не применяется"}{source.license_spdx === null ? "" : ` · ${source.license_spdx}`}</dd></div>
        <div><dt>Parser version</dt><dd>{source.adapter_version}</dd></div>
        <div><dt>Revision policy</dt><dd>{source.default_revision_policy}</dd></div>
      </dl>
      {source.attribution_template === null ? null : <p><strong>Attribution:</strong> {source.attribution_template}</p>}
      {source.status === "active" ? null : <p className="muted">{source.disable_reason === "owner_denied_usage" ? "Использование запрещено владельцем источника." : "Источник недоступен для запуска импорта."}</p>}
      <div className="inline-actions">
        {repositoryUrl === null ? null : <a href={repositoryUrl} target="_blank" rel="noopener noreferrer">Официальный repository ↗</a>}
        {licenseUrl === null ? null : <a href={licenseUrl} target="_blank" rel="noopener noreferrer">Официальная лицензия ↗</a>}
      </div>
    </article>
  );
}

export function SourcesPage() {
  const sources = useQuery(catalogSourcesQuery);
  if (sources.isPending) return <LoadingState label="Загружаем реестр источников…" />;
  if (sources.isError) return <ErrorState message="Backend не вернул реестр источников." onRetry={() => { void sources.refetch(); }} />;
  const active = sources.data.filter((source) => source.status === "active");
  const inactive = sources.data.filter((source) => source.status !== "active");
  return (
    <article className="sources-page">
      <header><p className="eyebrow">Прозрачность данных</p><h1>Источники и лицензии</h1><p className="lede">Код приложения и импортированные данные лицензируются раздельно. Каждая опубликованная карточка сохраняет собственный immutable source snapshot.</p></header>
      <section><p className="section-kicker">Разрешены для импорта</p><h2>Активные источники</h2><div className="source-grid">{active.map((source) => <SourceCard key={source.key} source={source} />)}</div></section>
      {inactive.length === 0 ? null : <section><p className="section-kicker">Read-only registry</p><h2>Неактивные источники</h2><p>Эти записи показаны только для прозрачности и не доступны на странице импорта.</p><div className="source-grid">{inactive.map((source) => <SourceCard key={source.key} source={source} />)}</div></section>}
    </article>
  );
}
