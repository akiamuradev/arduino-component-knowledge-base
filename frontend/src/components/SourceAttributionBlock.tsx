import type { ContentProvenance, SourceAttribution } from "../api/contracts";

const contentLabels: Record<ContentProvenance["contentType"], string> = {
  description: "Описание",
  specification: "Характеристики",
  image: "Изображение",
  diagram: "Схема",
  code: "Код",
  video: "Видео",
  document: "Документ",
};

function safeSourceUrl(source: SourceAttribution): string | undefined {
  try {
    const parsed = new URL(source.sourceUrl);
    return parsed.protocol === "https:" && parsed.hostname === source.sourceDomain
      ? parsed.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf())
    ? value
    : new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "long", year: "numeric" }).format(date);
}

function SourceLink({ source }: { source: SourceAttribution }) {
  const url = safeSourceUrl(source);
  return url === undefined ? (
    <span>{source.sourceName} · {source.sourceDomain}</span>
  ) : (
    <a href={url} target="_blank" rel="noopener noreferrer">
      {source.sourceName} <span aria-hidden="true">↗</span><span className="sr-only"> (откроется в новой вкладке)</span>
    </a>
  );
}

export function SourceAttributionBlock({ provenance }: { provenance: ContentProvenance[] }) {
  if (provenance.length === 0) return null;
  const single = provenance.length === 1 ? provenance[0] : undefined;
  return (
    <section className="source-attribution" aria-labelledby="source-attribution-title">
      <p className="section-kicker">Происхождение</p>
      <h2 id="source-attribution-title">{single === undefined ? "Источники материала" : "Источник материала"}</h2>
      {single === undefined ? (
        <ul>{provenance.map((item) => <li key={item.id}><strong>{contentLabels[item.contentType]}</strong><SourceLink source={item.source} />{item.source.contentLicense ? <small>{item.source.contentLicense}</small> : null}</li>)}</ul>
      ) : (
        <div className="source-attribution__single"><SourceLink source={single.source} /><span>Оригинальная публикация: {single.source.originalTitle ?? single.source.sourceDomain}</span><small>Импортировано: {formatDate(single.source.importedAt)}</small>{single.source.attributionText ? <p>{single.source.attributionText}</p> : null}</div>
      )}
    </section>
  );
}
