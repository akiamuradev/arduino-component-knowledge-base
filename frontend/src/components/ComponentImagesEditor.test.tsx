import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  Category,
  ComponentCard,
  ComponentMedia,
  MediaAsset,
} from "../api/contracts";
import { createQueryClient } from "../app/query-client";
import { ComponentImagesEditor } from "./ComponentImagesEditor";

const category: Category = {
  id: "00000000-0000-0000-0000-000000000020",
  slug: "boards",
  name: "Платы",
};

const firstImage: ComponentMedia = {
  asset_id: "10000000-0000-4000-8000-000000000001",
  kind: "image",
  purpose: "product",
  alt_text: "Вид платы сверху",
  caption: "Основной вид",
  display_order: 0,
  is_primary: true,
  status: "ready",
  width: 640,
  height: 480,
  variants: [{
    name: "320w",
    mime: "image/webp",
    width: 320,
    height: 240,
    sha256: "1".repeat(64),
  }],
};

const secondImage: ComponentMedia = {
  ...firstImage,
  asset_id: "10000000-0000-4000-8000-000000000002",
  purpose: "detail",
  alt_text: "Разъёмы платы",
  caption: null,
  display_order: 1,
  is_primary: false,
};

const card: ComponentCard = {
  id: "00000000-0000-0000-0000-000000000030",
  slug: "arduino-uno",
  status: "draft",
  title: "Arduino Uno",
  aliases: [],
  manufacturer: "Arduino",
  model: "A000066",
  primary_category: category,
  primary_category_id: category.id,
  tags: [],
  summary: "Учебная плата на базе микроконтроллера ATmega328P.",
  description: "Безопасное текстовое описание платы.",
  purpose: null,
  usage_notes: null,
  safety_notes: null,
  difficulty: "beginner",
  teacher_notes: null,
  manual_original: true,
  published_at: null,
  revision: 7,
  updated_at: "2026-07-23T05:00:00Z",
  sources: [],
  specifications: [],
  compatibility: [],
  code_examples: [],
  media: [firstImage, secondImage],
};

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

function requestBody(options: RequestInit | undefined): string {
  if (typeof options?.body !== "string") {
    throw new Error("Expected a JSON string request body");
  }
  return options.body;
}

function asset(image: ComponentMedia): MediaAsset {
  const firstVariant = image.variants[0];
  return {
    id: image.asset_id,
    kind: "image",
    component_id: card.id,
    purpose: image.purpose,
    alt_text: image.alt_text,
    caption: image.caption,
    display_order: image.display_order,
    is_primary: image.is_primary,
    status: image.status,
    declared_mime: "image/png",
    detected_mime: image.status === "ready" ? "image/png" : null,
    size_bytes: image.status === "ready" ? 100 : null,
    sha256: image.status === "ready" ? "2".repeat(64) : null,
    phash: image.status === "ready" ? "3".repeat(16) : null,
    width: image.width,
    height: image.height,
    duration_ms: null,
    video_codec: null,
    audio_codec: null,
    frame_rate: null,
    failure_code: null,
    job_status: image.status === "ready" ? "succeeded" : "queued",
    phase: image.status === "ready" ? "completed" : "queued",
    progress_percent: image.status === "ready" ? 100 : 0,
    variants: image.status === "ready" && firstVariant !== undefined
      ? [{
          ...firstVariant,
          size_bytes: 80,
          duration_ms: null,
          video_codec: null,
          audio_codec: null,
          frame_rate: null,
          url: `/media-storage/variants/${image.asset_id}/320w.webp?signed=1`,
        }]
      : [],
  };
}

function Harness({
  initialCard = card,
  saved,
}: {
  initialCard?: ComponentCard;
  saved: (value: ComponentCard) => void;
}) {
  const [current, setCurrent] = useState(initialCard);
  const [images, setImages] = useState(initialCard.media ?? []);
  const [dirty, setDirty] = useState(false);
  return (
    <ComponentImagesEditor
      card={current}
      dirty={dirty}
      images={images}
      onChange={(next) => {
        setImages(next);
        setDirty(true);
      }}
      onReload={() => Promise.resolve(undefined)}
      onSaved={(next) => {
        setCurrent(next);
        setImages(next.media ?? []);
        setDirty(false);
        saved(next);
      }}
    />
  );
}

function renderEditor(
  saved: (value: ComponentCard) => void,
  initialCard: ComponentCard = card,
) {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({
    queries: { retry: false, staleTime: Infinity },
    mutations: { retry: false },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <Harness initialCard={initialCard} saved={saved} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("component images editor", () => {
  it("persists metadata, primary choice and accessible ordering", async () => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const saved = vi.fn<(value: ComponentCard) => void>();
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input, options) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.includes("/api/v1/media/images/")) {
        const image = url.includes(firstImage.asset_id) ? firstImage : secondImage;
        return jsonResponse(asset(image));
      }
      if (url.endsWith(`/workspace/components/${card.id}/images`)) {
        const body = JSON.parse(requestBody(options)) as {
          images: { asset_id: string; purpose: string; alt_text: string; caption: string | null }[];
          primary_asset_id: string;
        };
        const media = body.images.map((item, index) => ({
          ...(item.asset_id === firstImage.asset_id ? firstImage : secondImage),
          ...item,
          display_order: index,
          is_primary: item.asset_id === body.primary_asset_id,
        }));
        return jsonResponse({ ...card, revision: 8, media });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(saved);

    await screen.findAllByText("Готово");
    await userEvent.clear(screen.getByLabelText("Alt изображения 2"));
    await userEvent.type(screen.getByLabelText("Alt изображения 2"), "Новый alt разъёмов");
    await userEvent.type(screen.getByLabelText("Подпись изображения 2"), "Крупный план");
    await userEvent.click(screen.getByLabelText("Основное изображение 2"));
    await userEvent.click(screen.getByRole("button", {
      name: "Переместить изображение 2 выше",
    }));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить изображения" }));

    await waitFor(() => { expect(saved).toHaveBeenCalledOnce(); });
    const mutation = fetchMock.mock.calls.find(([url, options]) =>
      requestUrl(url).endsWith(`/workspace/components/${card.id}/images`)
      && options?.method === "PUT");
    const body = JSON.parse(requestBody(mutation?.[1])) as {
      revision: number;
      images: { asset_id: string; alt_text: string; caption: string | null }[];
      primary_asset_id: string;
    };
    expect(body.revision).toBe(7);
    expect(body.images.map((item) => item.asset_id)).toEqual([
      secondImage.asset_id,
      firstImage.asset_id,
    ]);
    expect(body.images[0]).toEqual(expect.objectContaining({
      alt_text: "Новый alt разъёмов",
      caption: "Крупный план",
    }));
    expect(body.primary_asset_id).toBe(secondImage.asset_id);
  });

  it("keeps add and dropzone available after sequential uploads", async () => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const initialCard = { ...card, media: [firstImage] };
    const added: ComponentMedia[] = [
      {
        ...secondImage,
        asset_id: "10000000-0000-4000-8000-000000000003",
        alt_text: "front",
        status: "pending",
      },
      {
        ...secondImage,
        asset_id: "10000000-0000-4000-8000-000000000004",
        alt_text: "back",
        display_order: 2,
        status: "pending",
      },
    ];
    let reservation = 0;
    let workspaceRead = 0;
    const saved = vi.fn<(value: ComponentCard) => void>();
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input, options) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.startsWith("/media-storage/")) return new Response(null, { status: 200 });
      if (url === "/api/v1/media/images/uploads") {
        const image = added[reservation];
        if (image === undefined) throw new Error("Unexpected extra reservation");
        reservation += 1;
        return jsonResponse({
          asset_id: image.asset_id,
          upload_url: `/media-storage/quarantine/${image.asset_id}?signed=1`,
          upload_headers: { "Content-Type": "image/png" },
          expires_at: "2026-07-23T06:00:00Z",
          component_revision: 7 + reservation,
        }, 201);
      }
      if (url.endsWith("/complete")) {
        return jsonResponse({ asset_id: "asset", job_id: "job", status: "queued" });
      }
      if (url === `/api/v1/workspace/components/${card.id}`) {
        workspaceRead += 1;
        return jsonResponse({
          ...card,
          revision: 7 + workspaceRead,
          media: [firstImage, ...added.slice(0, workspaceRead)].map((image, index) => ({
            ...image,
            display_order: index,
          })),
        });
      }
      if (url.includes("/api/v1/media/images/")) {
        const image = [firstImage, ...added].find((item) => url.includes(item.asset_id));
        if (image !== undefined) return jsonResponse(asset(image));
      }
      throw new Error(`Unexpected request: ${url} ${String(options?.method)}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(saved, initialCard);

    const input = screen.getByLabelText("Добавить изображения", { selector: "input" });
    await userEvent.upload(input, [
      new File(["front"], "front.png", { type: "image/png" }),
      new File(["back"], "back.png", { type: "image/png" }),
    ]);

    expect(await screen.findByText("3 / 12")).toBeVisible();
    expect(screen.getByRole("button", { name: "Добавить изображения" })).toBeEnabled();
    expect(screen.getByText("Зона загрузки остаётся доступной после добавления файлов")).toBeVisible();
    const reserveBodies = fetchMock.mock.calls
      .filter(([url]) => requestUrl(url) === "/api/v1/media/images/uploads")
      .map(([, options]) => JSON.parse(requestBody(options)) as { component_revision: number });
    expect(reserveBodies.map((body) => body.component_revision)).toEqual([7, 8]);
    expect(saved).toHaveBeenCalledWith(expect.objectContaining({ revision: 9 }));
  });

  it("removes an image and lets backend-normalized first remaining image become primary", async () => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const saved = vi.fn<(value: ComponentCard) => void>();
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.includes("/api/v1/media/images/")) {
        return jsonResponse(asset(url.includes(firstImage.asset_id) ? firstImage : secondImage));
      }
      if (url.endsWith(`/workspace/components/${card.id}/images`)) {
        return jsonResponse({
          ...card,
          revision: 8,
          media: [{ ...secondImage, display_order: 0, is_primary: true }],
        });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(saved);

    await screen.findAllByText("Готово");
    await userEvent.click(screen.getByRole("button", {
      name: "Убрать изображение 1 из карточки",
    }));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить изображения" }));

    await waitFor(() => { expect(saved).toHaveBeenCalledOnce(); });
    const mutation = fetchMock.mock.calls.find(([url, options]) =>
      requestUrl(url).endsWith(`/workspace/components/${card.id}/images`)
      && options?.method === "PUT");
    const body = JSON.parse(requestBody(mutation?.[1])) as {
      images: { asset_id: string }[];
      primary_asset_id: string;
    };
    expect(body.images).toEqual([{ asset_id: secondImage.asset_id, purpose: "detail", alt_text: "Разъёмы платы", caption: null }]);
    expect(body.primary_asset_id).toBe(secondImage.asset_id);
  });

  it("preserves local order on revision conflict and offers explicit reload", async () => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const saved = vi.fn<(value: ComponentCard) => void>();
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input, options) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.includes("/api/v1/media/images/")) {
        return jsonResponse(asset(url.includes(firstImage.asset_id) ? firstImage : secondImage));
      }
      if (
        url.endsWith(`/workspace/components/${card.id}/images`)
        && options?.method === "PUT"
      ) {
        return jsonResponse({ detail: { code: "revision_conflict" } }, 409);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(saved);

    await screen.findAllByText("Готово");
    await userEvent.click(screen.getByRole("button", {
      name: "Переместить изображение 2 выше",
    }));
    await userEvent.click(screen.getByRole("button", { name: "Сохранить изображения" }));

    expect(await screen.findByText(/Локальный порядок и metadata сохранены/)).toBeVisible();
    const altFields = screen.getAllByLabelText(/^Alt изображения/);
    expect(altFields[0]).toHaveValue(secondImage.alt_text);
    expect(screen.getByRole("button", { name: "Загрузить серверную revision" })).toBeVisible();
    expect(saved).not.toHaveBeenCalled();
  });
});
