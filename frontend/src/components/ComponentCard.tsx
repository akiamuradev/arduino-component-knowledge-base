import { Link } from "react-router-dom";

import type { CatalogComponent, Difficulty } from "../api/contracts";
import { BrandSplat } from "./BrandSplat";

const difficultyLabels: Record<Difficulty, string> = {
  beginner: "Начальный",
  intermediate: "Средний",
  advanced: "Продвинутый",
};

function preferredImage(component: CatalogComponent): string | undefined {
  const image = component.media?.find((item) => item.kind === "image");
  const candidate = image?.thumbnailUrl ?? image?.processedUrl ?? image?.originalUrl;
  if (candidate === undefined) return undefined;
  try {
    const parsed = new URL(candidate, window.location.origin);
    return parsed.protocol === "https:" || parsed.origin === window.location.origin
      ? parsed.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

function specification(component: CatalogComponent, patterns: RegExp[]): string | undefined {
  const item = component.specifications.find((candidate) =>
    patterns.some((pattern) => pattern.test(`${candidate.key} ${candidate.label}`)),
  );
  return item === undefined ? undefined : `${item.value_text}${item.unit ? ` ${item.unit}` : ""}`;
}

export function ComponentCard({ component }: { component: CatalogComponent }) {
  const image = preferredImage(component);
  const voltage = specification(component, [/voltage/i, /напряж/i, /питан/i]);
  const componentInterface = specification(component, [/interface/i, /интерфейс/i, /protocol/i]);
  const sourceLabel = component.sources.length === 0
    ? null
    : component.sources.length === 1
      ? `Проверенный источник · ${component.sources[0]?.license_spdx ?? ""}`
      : `Несколько источников · ${String(component.sources.length)}`;
  return (
    <Link className="catalog-card" to={`/components/${component.slug}`}>
      <div className="catalog-card__media">
        {image === undefined ? <span className="catalog-card__fallback" role="img" aria-label={`Изображение для ${component.title} пока не добавлено`}><BrandSplat size="8.5rem" opacity={0.62} rotation={-6} variant="muted" /><b aria-hidden="true">{component.title.charAt(0).toUpperCase()}</b></span> : <img alt={component.media?.find((item) => item.kind === "image")?.alt ?? component.title} loading="lazy" src={image} />}
        <span className="status-badge">{component.primary_category.name}</span>
      </div>
      <div className="catalog-card__body">
        <div className="catalog-card__top"><h2>{component.title}</h2><span className="catalog-card__arrow" aria-hidden="true">↗</span></div>
        <p>{component.summary}</p>
        {component.tags.length > 0 ? <div className="tag-list">{component.tags.slice(0, 3).map((tag) => <span key={tag}>{tag}</span>)}</div> : null}
        <dl className="catalog-card__facts">
          {component.model ? <div><dt>Модель</dt><dd>{component.model}</dd></div> : null}
          {voltage ? <div><dt>Питание</dt><dd>{voltage}</dd></div> : null}
          {componentInterface ? <div><dt>Интерфейс</dt><dd>{componentInterface}</dd></div> : null}
        </dl>
        <footer><small><span aria-hidden="true">◉</span> {difficultyLabels[component.difficulty]}</small>{sourceLabel === null ? null : <small className="catalog-card__source">{sourceLabel}</small>}</footer>
      </div>
    </Link>
  );
}
