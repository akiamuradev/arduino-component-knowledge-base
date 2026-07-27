import {
  type KeyboardEvent,
  useMemo,
  useRef,
  useState,
} from "react";

import type { CatalogMedia, CatalogMediaVariant } from "../api/contracts";

function safeMediaUrl(value: string): string | undefined {
  try {
    const parsed = new URL(value, window.location.origin);
    return parsed.protocol === "https:" || parsed.origin === window.location.origin
      ? parsed.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

function orderedImages(items: CatalogMedia[]): CatalogMedia[] {
  return items
    .filter((item) => item.kind === "image")
    .sort((left, right) => {
      if (left.is_primary !== right.is_primary) return left.is_primary ? -1 : 1;
      return left.display_order - right.display_order;
    });
}

function safeVariants(item: CatalogMedia): (CatalogMediaVariant & { safeUrl: string })[] {
  return item.variants
    .flatMap((variant) => {
      const safeUrl = safeMediaUrl(variant.url);
      return safeUrl === undefined ? [] : [{ ...variant, safeUrl }];
    })
    .sort((left, right) => left.width - right.width);
}

function fallback(alt: string, compact = false) {
  return (
    <div
      aria-hidden={compact ? true : undefined}
      aria-label={compact ? undefined : alt}
      className={`media-fallback${compact ? " media-fallback--compact" : ""}`}
      role={compact ? undefined : "img"}
    >
      <span aria-hidden="true">▧</span>
      <small>Изображение недоступно</small>
    </div>
  );
}

function GalleryImage({
  active,
}: {
  active: CatalogMedia;
}) {
  const [failedUrl, setFailedUrl] = useState<string>();
  const variants = safeVariants(active);
  const largest = variants.at(-1);
  return (
    <figure className="media-gallery__primary">
      {largest === undefined || failedUrl === largest.safeUrl
        ? fallback(active.alt_text)
        : (
            <img
              alt={active.alt_text}
              decoding="async"
              fetchPriority="high"
              height={active.height ?? undefined}
              onError={() => { setFailedUrl(largest.safeUrl); }}
              sizes="(max-width: 767px) 100vw, 42vw"
              src={largest.safeUrl}
              srcSet={variants
                .map((variant) => `${variant.safeUrl} ${String(variant.width)}w`)
                .join(", ") || undefined}
              width={active.width ?? undefined}
            />
          )}
      {active.caption === null ? null : <figcaption>{active.caption}</figcaption>}
    </figure>
  );
}

function GalleryThumbnail({
  image,
  index,
  selected,
  onSelect,
  buttonRef,
}: {
  image: CatalogMedia;
  index: number;
  selected: boolean;
  onSelect: () => void;
  buttonRef: (element: HTMLButtonElement | null) => void;
}) {
  const [failedUrl, setFailedUrl] = useState<string>();
  const thumbnail = safeVariants(image)[0];
  return (
    <button
      aria-label={`Показать изображение ${String(index + 1)}: ${image.alt_text}`}
      aria-pressed={selected}
      className="media-gallery__thumbnail"
      onClick={onSelect}
      ref={buttonRef}
      type="button"
    >
      {thumbnail === undefined || failedUrl === thumbnail.safeUrl
        ? fallback(image.alt_text, true)
        : (
            <img
              alt=""
              decoding="async"
              height={thumbnail.height}
              loading="lazy"
              onError={() => { setFailedUrl(thumbnail.safeUrl); }}
              src={thumbnail.safeUrl}
              width={thumbnail.width}
            />
          )}
      <span>{String(index + 1).padStart(2, "0")}</span>
    </button>
  );
}

function GalleryVideo({ item }: { item: CatalogMedia }) {
  const [failedUrl, setFailedUrl] = useState<string>();
  const source = safeVariants(item).at(-1);
  return (
    <figure className="media-gallery__video">
      {source === undefined || failedUrl === source.safeUrl
        ? fallback(item.alt_text)
        : (
            <video
              aria-label={item.alt_text}
              controls
              onError={() => { setFailedUrl(source.safeUrl); }}
              preload="metadata"
            >
              <source src={source.safeUrl} type={source.mime} />
            </video>
          )}
      {item.caption === null ? null : <figcaption>{item.caption}</figcaption>}
    </figure>
  );
}

export function MediaGallery({ items }: { items: CatalogMedia[] }) {
  const images = useMemo(() => orderedImages(items), [items]);
  const videos = useMemo(
    () => items
      .filter((item) => item.kind === "video")
      .sort((left, right) => left.display_order - right.display_order),
    [items],
  );
  const [activeId, setActiveId] = useState<string>();
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIndex = Math.max(
    0,
    images.findIndex((item) => item.asset_id === activeId),
  );
  const active = images[activeIndex];

  if (active === undefined && videos.length === 0) return null;

  const select = (index: number, focus = false) => {
    const next = images[index];
    if (next === undefined) return;
    setActiveId(next.asset_id);
    if (focus) buttonRefs.current[index]?.focus();
  };
  const move = (direction: -1 | 1, focus = false) => {
    if (images.length === 0) return;
    select((activeIndex + direction + images.length) % images.length, focus);
  };
  const keyboard = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1, true);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1, true);
    } else if (event.key === "Home") {
      event.preventDefault();
      select(0, true);
    } else if (event.key === "End") {
      event.preventDefault();
      select(images.length - 1, true);
    }
  };

  return (
    <section
      aria-label={active === undefined
        ? "Медиа компонента"
        : "Галерея изображений компонента"}
      className="media-gallery"
      onKeyDown={active === undefined ? undefined : keyboard}
    >
      {active === undefined ? null : <GalleryImage active={active} />}
      {active === undefined || images.length < 2 ? null : (
        <>
          <div className="media-gallery__navigation">
            <span aria-live="polite">
              Изображение {String(activeIndex + 1)} из {String(images.length)}
            </span>
            <div>
              <button
                aria-label="Предыдущее изображение"
                className="button button--quiet"
                onClick={() => { move(-1); }}
                type="button"
              >
                ←
              </button>
              <button
                aria-label="Следующее изображение"
                className="button button--quiet"
                onClick={() => { move(1); }}
                type="button"
              >
                →
              </button>
            </div>
          </div>
          <div
            aria-label="Миниатюры изображений"
            className="media-gallery__thumbnails"
            role="group"
          >
            {images.map((image, index) => (
              <GalleryThumbnail
                buttonRef={(element) => { buttonRefs.current[index] = element; }}
                image={image}
                index={index}
                key={image.asset_id}
                onSelect={() => { select(index); }}
                selected={index === activeIndex}
              />
            ))}
          </div>
        </>
      )}
      {videos.length === 0 ? null : (
        <div className="media-gallery__videos">
          {videos.map((video) => (
            <GalleryVideo item={video} key={video.asset_id} />
          ))}
        </div>
      )}
    </section>
  );
}
