import { useMutation, useQuery } from "@tanstack/react-query";
import {
  type ChangeEvent,
  type DragEvent,
  useEffect,
  useRef,
  useState,
} from "react";

import type {
  ComponentCard,
  ComponentMedia,
  MediaAsset,
} from "../api/contracts";
import { api, ApiError, uploadReservedFile } from "../api/client";

const MAX_COMPONENT_IMAGES = 12;
const MAX_IMAGE_BYTES = 8 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

interface ComponentImagesEditorProps {
  card?: ComponentCard;
  images: ComponentMedia[];
  dirty: boolean;
  onChange: (images: ComponentMedia[]) => void;
  onSaved: (card: ComponentCard) => void;
  onReload?: () => Promise<void>;
}

function normalizeImages(images: ComponentMedia[]): ComponentMedia[] {
  if (images.length === 0) return [];
  const currentPrimary = images.find((image) => image.is_primary)?.asset_id;
  const primary = currentPrimary ?? images[0]?.asset_id;
  return images.map((image, index) => ({
    ...image,
    display_order: index,
    is_primary: image.asset_id === primary,
  }));
}

function mutationPayload(images: ComponentMedia[]) {
  const normalized = normalizeImages(images);
  return {
    images: normalized.map((image) => ({
      asset_id: image.asset_id,
      purpose: image.purpose.trim(),
      alt_text: image.alt_text.trim(),
      caption: image.caption?.trim() === "" ? null : (image.caption?.trim() ?? null),
    })),
    primary_asset_id: normalized.find((image) => image.is_primary)?.asset_id ?? null,
  };
}

function fallbackAlt(file: File): string {
  const withoutExtension = file.name.replace(/\.[^.]+$/, "");
  const normalized = withoutExtension.replace(/[_-]+/g, " ").trim();
  return normalized || "Изображение компонента";
}

function validateFiles(files: File[], occupied: number): string | undefined {
  if (files.length === 0) return undefined;
  if (occupied + files.length > MAX_COMPONENT_IMAGES) {
    return `В карточке может быть не более ${String(MAX_COMPONENT_IMAGES)} изображений.`;
  }
  const unsupported = files.find((file) => !ALLOWED_IMAGE_TYPES.has(file.type));
  if (unsupported !== undefined) {
    return `Файл «${unsupported.name}» должен быть JPEG, PNG или WebP.`;
  }
  const invalidSize = files.find(
    (file) => file.size === 0 || file.size > MAX_IMAGE_BYTES,
  );
  if (invalidSize !== undefined) {
    return `Файл «${invalidSize.name}» должен быть от 1 байта до 8 МиБ.`;
  }
  return undefined;
}

function safeMediaUrl(value: string | undefined): string | undefined {
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

function statusLabel(asset: MediaAsset | undefined, fallback: ComponentMedia): string {
  const status = asset?.status ?? fallback.status;
  if (status === "ready") return "Готово";
  if (status === "rejected") return "Отклонено";
  if (status === "processing") {
    const progress = asset?.progress_percent;
    return progress === null || progress === undefined
      ? "Обработка"
      : `Обработка · ${String(progress)}%`;
  }
  return "Ожидает обработки";
}

function ImageThumbnail({
  image,
  localPreview,
}: {
  image: ComponentMedia;
  localPreview?: string;
}) {
  const [failed, setFailed] = useState(false);
  const status = useQuery({
    queryKey: ["media", "image", image.asset_id],
    queryFn: () => api.getComponentImage(image.asset_id),
    refetchInterval: (query) => {
      const value = query.state.data?.status;
      return value === "ready" || value === "rejected" ? false : 1500;
    },
  });
  const variant = status.data?.variants.find((item) => item.name === "320w")
    ?? status.data?.variants[0];
  const url = safeMediaUrl(variant?.url) ?? localPreview;
  const rejected = (status.data?.status ?? image.status) === "rejected";

  return (
    <div className="image-editor-card__preview">
      {failed || url === undefined ? (
        <div
          className="image-editor-card__fallback"
          role="img"
          aria-label={image.alt_text}
        >
          <span aria-hidden="true">▧</span>
          <small>{rejected ? "Файл отклонён" : "Превью готовится"}</small>
        </div>
      ) : (
        <img
          alt={image.alt_text}
          onError={() => { setFailed(true); }}
          src={url}
        />
      )}
      <span className={`image-status image-status--${status.data?.status ?? image.status}`}>
        {status.isError
          ? "Статус недоступен"
          : statusLabel(status.data, image)}
      </span>
      {status.data?.failure_code === null || status.data?.failure_code === undefined
        ? null
        : <small className="image-editor-card__error">{status.data.failure_code}</small>}
    </div>
  );
}

function errorLabel(error: unknown): string {
  if (!(error instanceof ApiError)) return "непредвиденная ошибка";
  const labels: Record<string, string> = {
    csrf_token_missing: "сессия не содержит CSRF-токен",
    image_declared_mime_not_allowed: "неподдерживаемый формат изображения",
    media_component_count_exceeded: "достигнут лимит изображений",
    media_component_size_exceeded: "достигнут лимит размера медиа",
    media_pending_quota_exceeded: "слишком много незавершённых загрузок",
    media_upload_failed: "MinIO не принял файл",
    media_enqueue_failed: "обработчик изображений временно недоступен",
    media_not_found: "изображение больше недоступно",
    component_image_metadata_invalid: "проверьте назначение, alt и подпись",
  };
  return labels[error.code] ?? error.code;
}

export function ComponentImagesEditor({
  card,
  images,
  dirty,
  onChange,
  onSaved,
  onReload,
}: ComponentImagesEditorProps) {
  const [validationError, setValidationError] = useState<string>();
  const [dragging, setDragging] = useState(false);
  const [localPreviews, setLocalPreviews] = useState<Record<string, string>>({});
  const previewsRef = useRef<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const orderedImages = [...images].sort(
    (left, right) => left.display_order - right.display_order,
  );

  useEffect(() => () => {
    for (const url of previewsRef.current) URL.revokeObjectURL(url);
  }, []);

  const persist = useMutation({
    mutationFn: async (nextImages: ComponentMedia[]) => {
      if (card === undefined) throw new Error("Save the draft before editing images");
      const payload = mutationPayload(nextImages);
      return api.updateComponentImages(card.id, {
        revision: card.revision,
        ...payload,
      });
    },
    onSuccess: onSaved,
  });

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      if (card === undefined) throw new Error("Save the draft before uploading images");
      let activeCard = card;
      try {
        if (dirty) {
          const payload = mutationPayload(orderedImages);
          activeCard = await api.updateComponentImages(activeCard.id, {
            revision: activeCard.revision,
            ...payload,
          });
        }
        for (const file of files) {
          const currentCount = activeCard.media?.length ?? 0;
          const reservation = await api.reserveComponentImage({
            component_id: activeCard.id,
            component_revision: activeCard.revision,
            purpose: currentCount === 0 ? "product" : "detail",
            alt_text: fallbackAlt(file),
            attribution: null,
            declared_mime: file.type,
            declared_size_bytes: file.size,
          });
          if (reservation.component_revision === null) {
            throw new Error("Backend did not return the component revision");
          }
          if (typeof URL.createObjectURL === "function") {
            const preview = URL.createObjectURL(file);
            previewsRef.current.push(preview);
            setLocalPreviews((current) => ({
              ...current,
              [reservation.asset_id]: preview,
            }));
          }
          await uploadReservedFile(reservation, file);
          await api.completeComponentImage(reservation.asset_id);
          activeCard = await api.getWorkspaceComponent(activeCard.id);
        }
        return activeCard;
      } catch (error) {
        try {
          onSaved(await api.getWorkspaceComponent(activeCard.id));
        } catch {
          // Keep the original typed upload error and let explicit reload recover.
        }
        throw error;
      }
    },
    onSuccess: onSaved,
  });

  const mutationError = persist.error ?? upload.error;
  const conflict = mutationError instanceof ApiError
    && mutationError.code === "revision_conflict";
  const atLimit = orderedImages.length >= MAX_COMPONENT_IMAGES;
  const busy = persist.isPending || upload.isPending;

  const chooseFiles = (files: File[]) => {
    const issue = validateFiles(files, orderedImages.length);
    setValidationError(issue);
    if (issue === undefined) upload.mutate(files);
  };
  const fileChange = (event: ChangeEvent<HTMLInputElement>) => {
    chooseFiles(Array.from(event.target.files ?? []));
    event.target.value = "";
  };
  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (!busy && !atLimit && card !== undefined) {
      chooseFiles(Array.from(event.dataTransfer.files));
    }
  };
  const changeImage = (
    assetId: string,
    patch: Partial<Pick<ComponentMedia, "purpose" | "alt_text" | "caption" | "is_primary">>,
  ) => {
    onChange(normalizeImages(orderedImages.map((image) => {
      if (image.asset_id === assetId) return { ...image, ...patch };
      return patch.is_primary === true ? { ...image, is_primary: false } : image;
    })));
  };
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= orderedImages.length) return;
    const next = [...orderedImages];
    const current = next[index];
    const neighbor = next[target];
    if (current === undefined || neighbor === undefined) return;
    next[index] = neighbor;
    next[target] = current;
    onChange(normalizeImages(next));
  };
  const remove = (assetId: string) => {
    onChange(normalizeImages(
      orderedImages.filter((image) => image.asset_id !== assetId),
    ));
  };

  return (
    <fieldset className="images-editor">
      <legend>Изображения</legend>
      <div className="images-editor__heading">
        <p className="field-help">
          До 12 файлов JPEG, PNG или WebP, каждый не больше 8 МиБ. Первое изображение
          backend назначает основным автоматически.
        </p>
        <span>{String(orderedImages.length)} / {String(MAX_COMPONENT_IMAGES)}</span>
      </div>

      {card === undefined ? (
        <div className="images-editor__locked">
          <strong>Сначала сохраните draft</strong>
          <span>Карточку можно сохранить без изображений, а затем добавить файлы.</span>
        </div>
      ) : (
        <div
          className={`image-dropzone${dragging ? " image-dropzone--active" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            if (!busy && !atLimit) setDragging(true);
          }}
          onDragLeave={() => { setDragging(false); }}
          onDragOver={(event) => { event.preventDefault(); }}
          onDrop={drop}
        >
          <input
            accept="image/jpeg,image/png,image/webp"
            aria-label="Добавить изображения"
            className="sr-only"
            disabled={busy || atLimit}
            id="component-image-upload"
            multiple
            onChange={fileChange}
            ref={inputRef}
            type="file"
          />
          <span aria-hidden="true" className="image-dropzone__icon">＋</span>
          <div>
            <strong>{upload.isPending ? "Загружаем изображения…" : "Перетащите изображения сюда"}</strong>
            <span>
              {atLimit
                ? "Достигнут лимит 12 изображений"
                : "Зона загрузки остаётся доступной после добавления файлов"}
            </span>
          </div>
          <button
            className="button button--quiet"
            disabled={busy || atLimit}
            onClick={() => { inputRef.current?.click(); }}
            type="button"
          >
            Добавить изображения
          </button>
        </div>
      )}

      {validationError === undefined
        ? null
        : <div className="inline-error" role="alert">{validationError}</div>}
      {mutationError === null
        ? null
        : (
          <div className={conflict ? "conflict-banner" : "inline-error"} role="alert">
            <span>
              {conflict
                ? "Revision карточки изменилась. Локальный порядок и metadata сохранены."
                : `Изображения не сохранены: ${errorLabel(mutationError)}.`}
            </span>
            {!conflict || onReload === undefined
              ? null
              : (
                <button
                  className="button button--quiet"
                  onClick={() => { void onReload(); }}
                  type="button"
                >
                  Загрузить серверную revision
                </button>
              )}
          </div>
        )}

      {orderedImages.length === 0 ? (
        <p className="images-editor__empty">
          Изображений пока нет. Это не мешает сохранять draft.
        </p>
      ) : (
        <div className="images-editor__list">
          {orderedImages.map((image, index) => (
            <article className="image-editor-card" key={image.asset_id}>
              <ImageThumbnail
                image={image}
                localPreview={localPreviews[image.asset_id]}
              />
              <div className="image-editor-card__fields">
                <label>
                  Назначение изображения {String(index + 1)}
                  <input
                    list="component-image-purposes"
                    maxLength={40}
                    onChange={(event) => {
                      changeImage(image.asset_id, { purpose: event.target.value });
                    }}
                    required
                    value={image.purpose}
                  />
                </label>
                <label>
                  Alt изображения {String(index + 1)}
                  <input
                    maxLength={500}
                    onChange={(event) => {
                      changeImage(image.asset_id, { alt_text: event.target.value });
                    }}
                    required
                    value={image.alt_text}
                  />
                </label>
                <label>
                  Подпись изображения {String(index + 1)}
                  <textarea
                    maxLength={1000}
                    onChange={(event) => {
                      changeImage(image.asset_id, {
                        caption: event.target.value || null,
                      });
                    }}
                    rows={2}
                    value={image.caption ?? ""}
                  />
                </label>
                <label className="image-editor-card__primary">
                  <input
                    checked={image.is_primary}
                    name="component-primary-image"
                    onChange={() => {
                      changeImage(image.asset_id, { is_primary: true });
                    }}
                    type="radio"
                  />
                  Основное изображение {String(index + 1)}
                </label>
              </div>
              <div className="image-editor-card__actions">
                <button
                  aria-label={`Переместить изображение ${String(index + 1)} выше`}
                  className="button button--quiet"
                  disabled={index === 0 || busy}
                  onClick={() => { move(index, -1); }}
                  type="button"
                >
                  ↑
                </button>
                <button
                  aria-label={`Переместить изображение ${String(index + 1)} ниже`}
                  className="button button--quiet"
                  disabled={index === orderedImages.length - 1 || busy}
                  onClick={() => { move(index, 1); }}
                  type="button"
                >
                  ↓
                </button>
                <button
                  aria-label={`Убрать изображение ${String(index + 1)} из карточки`}
                  className="button button--danger"
                  disabled={busy}
                  onClick={() => { remove(image.asset_id); }}
                  type="button"
                >
                  Убрать
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      <datalist id="component-image-purposes">
        <option value="product">Общий вид</option>
        <option value="detail">Деталь</option>
        <option value="connection">Подключение</option>
        <option value="pinout">Распиновка</option>
        <option value="scale">Масштаб</option>
        <option value="other">Другое</option>
      </datalist>

      {card === undefined ? null : (
        <div className="images-editor__footer">
          <button
            className="button button--primary"
            disabled={!dirty || busy}
            onClick={() => { persist.mutate(orderedImages); }}
            type="button"
          >
            {persist.isPending ? "Сохраняем изображения…" : "Сохранить изображения"}
          </button>
          <span>
            {dirty
              ? "Есть несохранённые изменения изображений."
              : "Порядок и metadata синхронизированы с backend."}
          </span>
        </div>
      )}
    </fieldset>
  );
}
