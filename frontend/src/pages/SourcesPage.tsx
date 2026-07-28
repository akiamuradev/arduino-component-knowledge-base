import { useQuery } from "@tanstack/react-query";

import type { CatalogSource } from "../api/contracts";
import { catalogSourcesQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";

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
  const sourceStatus = source.status === "active" ? "Активен" : "Неактивен";
  const sourceType = source.source_type === "git_repository"
    ? "Репозиторий Git"
    : source.source_type;
  const contentPolicy = source.content_policy === "licensed_content"
    ? "Лицензированные материалы"
    : source.content_policy === "metadata_only"
      ? "Только метаданные"
      : source.content_policy;
  const revisionPolicy = source.default_revision_policy === "pinned_tag"
    ? "Закреплённый тег"
    : source.default_revision_policy === "pinned_commit"
      ? "Закреплённый коммит"
      : source.default_revision_policy === "default_branch"
        ? "Основная ветка"
        : source.default_revision_policy;
  return (
    <article className="source-card">
      <div className="section-heading"><div><p className="section-kicker">Тип: {sourceType}</p><h2>{source.display_name}</h2></div><span className={`status-badge status-badge--${source.status}`}>{sourceStatus}</span></div>
      <dl className="source-facts">
        <div><dt>Назначение</dt><dd>{contentPolicy}</dd></div>
        <div><dt>Лицензия</dt><dd>{source.license_name ?? "Не применяется"}{source.license_spdx === null ? "" : ` · ${source.license_spdx}`}</dd></div>
        <div><dt>Версия импорта</dt><dd>{source.adapter_version}</dd></div>
        <div><dt>Правило выбора версии</dt><dd>{revisionPolicy}</dd></div>
      </dl>
      {source.attribution_template === null ? null : <p><strong>Сведения об авторстве:</strong> {source.attribution_template}</p>}
      {source.status === "active" ? null : <p className="muted">{source.disable_reason === "owner_denied_usage" ? "Использование запрещено владельцем источника." : "Источник недоступен для запуска импорта."}</p>}
      <div className="inline-actions">
        {repositoryUrl === null ? null : <a href={repositoryUrl} target="_blank" rel="noopener noreferrer">Официальный репозиторий ↗</a>}
        {licenseUrl === null ? null : <a href={licenseUrl} target="_blank" rel="noopener noreferrer">Официальная лицензия ↗</a>}
      </div>
    </article>
  );
}

export function SourcesPage() {
  const sources = useQuery(catalogSourcesQuery);
  if (sources.isPending) return <LoadingState label="Загружаем реестр источников…" />;
  if (sources.isError) return <ErrorState message="Не удалось загрузить реестр источников. Попробуйте снова." onRetry={() => { void sources.refetch(); }} />;
  const active = sources.data.filter((source) => source.status === "active");
  const inactive = sources.data.filter((source) => source.status !== "active");
  return (
    <article className="sources-page">
      <header><p className="eyebrow">Прозрачность данных</p><h1>Источники и лицензии</h1><p className="lede">Код приложения и импортированные данные лицензируются раздельно. Каждая опубликованная карточка сохраняет неизменяемый снимок своего источника.</p></header>
      <section><p className="section-kicker">Разрешены для импорта</p><h2>Активные источники</h2>{active.length === 0 ? <SplatEmptyState icon="◇" title="Активных источников пока нет" description="Импорт станет доступен после настройки хотя бы одного источника." /> : <div className="source-grid">{active.map((source) => <SourceCard key={source.key} source={source} />)}</div>}</section>
      {inactive.length === 0 ? null : <section><p className="section-kicker">Реестр только для чтения</p><h2>Неактивные источники</h2><p>Эти записи показаны только для прозрачности и недоступны на странице импорта.</p><div className="source-grid">{inactive.map((source) => <SourceCard key={source.key} source={source} />)}</div></section>}
    </article>
  );
}
