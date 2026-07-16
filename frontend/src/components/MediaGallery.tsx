import { useState } from "react";

import type { CatalogMedia } from "../api/contracts";

function mediaUrl(item: CatalogMedia): string | undefined {
  return item.thumbnailUrl ?? item.processedUrl ?? item.originalUrl;
}

function safeHref(value: string | undefined): string | undefined {
  if (value === undefined) return undefined;
  try {
    const parsed = new URL(value, window.location.origin);
    return parsed.protocol === "https:" || parsed.origin === window.location.origin
      ? parsed.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

function MediaItem({ item }: { item: CatalogMedia }) {
  const [failed, setFailed] = useState(false);
  const url = safeHref(mediaUrl(item));
  const sourceUrl = safeHref(item.source?.sourceUrl);
  if (failed || url === undefined) {
    return <div className="media-fallback" role="img" aria-label={item.alt}><span aria-hidden="true">▧</span><small>Медиа недоступно</small></div>;
  }
  return (
    <figure className="media-item">
      {item.kind === "image" ? (
        <img alt={item.alt} loading="lazy" onError={() => { setFailed(true); }} src={url} />
      ) : (
        <video aria-label={item.alt} controls onError={() => { setFailed(true); }} poster={safeHref(item.posterUrl)} preload="metadata"><source src={url} /></video>
      )}
      {item.source !== undefined && sourceUrl !== undefined ? <figcaption><a href={sourceUrl} target="_blank" rel="noopener noreferrer">Источник {item.kind === "image" ? "изображения" : "видео"} <span aria-hidden="true">↗</span></a></figcaption> : null}
    </figure>
  );
}

export function MediaGallery({ items }: { items: CatalogMedia[] }) {
  if (items.length === 0) return null;
  return <section className="media-gallery" aria-label="Медиа компонента">{items.map((item) => <MediaItem item={item} key={item.id} />)}</section>;
}
