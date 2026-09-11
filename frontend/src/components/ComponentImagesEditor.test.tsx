import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  archived_from_status: null,
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
  const [images, setImages] = useState(initialCard.media ?? []);
  return (
    <ComponentImagesEditor
      card={initialCard}
      images={images}
      onChange={(next) => {
        setImages(next);
        saved({ ...initialCard, media: next });
      }}
      onUploaded={(image) => {
        setImages((current) => [...current, { ...image, display_order: current.length,
          is_primary: current.length === 0 }]);
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
  return queryClient;
}

function renderStagedEditor() {
  function StagedHarness() {
    const [images, setImages] = useState<ComponentMedia[]>([]);
    return (
      <ComponentImagesEditor
        card={undefined}
        images={images}
        onChange={(next) => {
          setImages(next);
        }}
        onUploaded={(image) => { setImages((current) => [...current, image]); }}
      />
    );
  }

  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({
    queries: { retry: false, staleTime: Infinity },
    mutations: { retry: false },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <StagedHarness />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("component images editor", () => {
  it.each([
    ["reservation", "Подготовка загрузки"],
    ["upload", "Отправка файла в хранилище"],
    ["confirmation", "Подтверждение загрузки"],
  ])("reports a safe %s-stage failure without exposing signed URLs", async (stage, label) => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url.endsWith("/uploads")) {
        if (stage === "reservation") return jsonResponse({ detail: { code: "media_upload_rate_limited" } }, 429);
        return jsonResponse({ asset_id: firstImage.asset_id,
          upload_url: "/media-storage/private?secret-signature=do-not-expose",
          upload_headers: { "Content-Type": "image/png" }, component_revision: null });
      }
      if (url.startsWith("/media-storage/")) return new Response(null, { status: stage === "upload" ? 503 : 200 });
      return jsonResponse({ detail: { code: "media_enqueue_failed" } }, 503);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(vi.fn(), { ...card, media: [] });
    await userEvent.upload(screen.getByLabelText("Добавить изображения", { selector: "input" }),
      new File(["bytes"], "uno.png", { type: "image/png" }));
    expect(await screen.findByText(new RegExp(label))).toBeVisible();
    expect(document.body.textContent).not.toContain("secret-signature");
    expect(fetchMock.mock.calls.some(([input]) => requestUrl(input).includes("workspace/components"))).toBe(false);
  });
  it("uploads and previews an image before the first draft save", async () => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const staged = {
      ...asset(firstImage),
      component_id: null,
      alt_text: "component front",
      status: "pending",
      detected_mime: null,
      size_bytes: null,
      sha256: null,
      phash: null,
      width: null,
      height: null,
      job_status: "queued",
      phase: "queued",
      progress_percent: 0,
      variants: [],
    } satisfies MediaAsset;
    const saved = vi.fn<(value: ComponentCard) => void>();
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url === "/api/v1/media/images/uploads") {
        return jsonResponse({
          asset_id: staged.id,
          upload_url: `/media-storage/quarantine/${staged.id}?signed=1`,
          upload_headers: { "Content-Type": "image/png" },
          expires_at: "2026-07-29T12:00:00Z",
          component_revision: null,
        }, 201);
      }
      if (url.startsWith("/media-storage/")) return new Response(null, { status: 200 });
      if (url.endsWith("/complete")) {
        return jsonResponse({ asset_id: staged.id, job_id: "job", status: "queued" });
      }
      if (url.endsWith(staged.id)) return jsonResponse(staged);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderStagedEditor();

    await userEvent.upload(
      screen.getByLabelText("Добавить изображения", { selector: "input" }),
      new File(["preview"], "component-front.png", { type: "image/png" }),
    );

    expect(await screen.findByText("1 / 12")).toBeVisible();
    expect(screen.getByText(/синхронизируются автоматически вместе с карточкой/)).toBeVisible();
    expect(screen.getByLabelText("Альтернативный текст изображения 1")).toHaveValue(
      "component front",
    );
    expect(screen.getByRole("button", { name: "Добавить изображения" })).toBeEnabled();
    expect(saved).not.toHaveBeenCalled();

    const reservation = fetchMock.mock.calls.find(
      ([input]) => requestUrl(input) === "/api/v1/media/images/uploads",
    );
    expect(JSON.parse(requestBody(reservation?.[1]))).toEqual(expect.objectContaining({
      component_id: null,
      component_revision: null,
      alt_text: "component front",
    }));
  });

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
    await userEvent.clear(screen.getByLabelText("Альтернативный текст изображения 2"));
    await userEvent.type(screen.getByLabelText("Альтернативный текст изображения 2"), "Новый текст разъёмов");
    await userEvent.type(screen.getByLabelText("Подпись изображения 2"), "Крупный план");
    await userEvent.click(screen.getByLabelText("Основное изображение 2"));
    await userEvent.click(screen.getByRole("button", {
      name: "Переместить изображение 2 выше",
    }));
    expect(screen.queryByRole("button", { name: "Сохранить изображения" })).not.toBeInTheDocument();
    const last = saved.mock.lastCall?.[0].media ?? [];
    expect(last.map((item) => item.asset_id)).toEqual([
      secondImage.asset_id,
      firstImage.asset_id,
    ]);
    expect(last[0]).toEqual(expect.objectContaining({
      alt_text: "Новый текст разъёмов",
      caption: "Крупный план",
    }));
    expect(last[0]?.is_primary).toBe(true);
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === "PUT")).toBe(false);
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
    expect(reserveBodies.map((body) => body.component_revision)).toEqual([null, null]);
    expect(workspaceRead).toBe(0);
  });

  it("shows pending, processing, ready, rejected and status error states", async () => {
    const sourceStates: ComponentMedia[] = [
      { ...firstImage, asset_id: "10000000-0000-4000-8000-000000000005" },
      {
        ...secondImage,
        asset_id: "10000000-0000-4000-8000-000000000006",
        status: "processing",
      },
      {
        ...secondImage,
        asset_id: "10000000-0000-4000-8000-000000000007",
        status: "pending",
      },
      {
        ...secondImage,
        asset_id: "10000000-0000-4000-8000-000000000008",
        status: "rejected",
      },
      {
        ...secondImage,
        asset_id: "10000000-0000-4000-8000-000000000009",
        status: "pending",
      },
    ];
    const states = sourceStates.map(
      (image, index): ComponentMedia => ({ ...image, display_order: index }),
    );
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      const image = states.find((item) => url.includes(item.asset_id));
      if (image === undefined) throw new Error(`Unexpected request: ${url}`);
      if (image.asset_id.endsWith("0009")) {
        return jsonResponse({ detail: { code: "media_status_unavailable" } }, 503);
      }
      const response = asset(image);
      if (image.status === "processing") {
        return jsonResponse({
          ...response,
          job_status: "running",
          phase: "uploading",
          progress_percent: 42,
        });
      }
      if (image.status === "rejected") {
        return jsonResponse({
          ...response,
          failure_code: "image_magic_invalid",
          job_status: "failed",
          phase: "failed",
        });
      }
      return jsonResponse(response);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(vi.fn(), { ...card, media: states });

    expect(await screen.findByText("Готово")).toBeVisible();
    expect(await screen.findByText("Обработка · 42%")).toBeVisible();
    expect(await screen.findByText("Ожидает обработки")).toBeVisible();
    expect(await screen.findByText("Отклонено")).toBeVisible();
    expect(
      await screen.findByText("Содержимое файла не соответствует формату изображения."),
    ).toBeVisible();
    expect(await screen.findByText("Состояние недоступно")).toBeVisible();
  });

  it("recovers a failed thumbnail when the backend renews its signed URL", async () => {
    const ready = asset(firstImage);
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(ready)));
    const queryClient = renderEditor(vi.fn(), { ...card, media: [firstImage] });
    act(() => {
      queryClient.setQueryData(["media", "image", firstImage.asset_id], ready);
    });

    const initial = await screen.findByAltText(firstImage.alt_text);
    fireEvent.error(initial);
    expect(await screen.findByText("Превью готовится")).toBeVisible();

    act(() => {
      queryClient.setQueryData(["media", "image", firstImage.asset_id], {
        ...ready,
        variants: ready.variants.map((variant) => ({
          ...variant,
          url: `${variant.url}&renewed=1`,
        })),
      });
    });
    expect(await screen.findByAltText(firstImage.alt_text)).toHaveAttribute(
      "src",
      expect.stringContaining("renewed=1"),
    );
  });

  it("keeps the editor usable after a storage upload error", async () => {
    document.cookie = "ackb_csrf=media-csrf; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (input) => {
      await Promise.resolve();
      const url = requestUrl(input);
      if (url === "/api/v1/media/images/uploads") {
        return jsonResponse({
          asset_id: "10000000-0000-4000-8000-000000000010",
          upload_url: "/media-storage/quarantine/failed?signed=1",
          upload_headers: { "Content-Type": "image/png" },
          expires_at: "2026-07-23T06:00:00Z",
          component_revision: 8,
        }, 201);
      }
      if (url.startsWith("/media-storage/")) return new Response(null, { status: 500 });
      if (url === `/api/v1/workspace/components/${card.id}`) {
        return jsonResponse(card);
      }
      if (url.includes("/api/v1/media/images/")) {
        return jsonResponse(asset(url.includes(firstImage.asset_id) ? firstImage : secondImage));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor(vi.fn());

    const input = screen.getByLabelText("Добавить изображения", { selector: "input" });
    await userEvent.upload(
      input,
      new File(["broken"], "broken.png", { type: "image/png" }),
    );

    expect(await screen.findByText(/не удалось загрузить файл, попробуйте снова/i)).toBeVisible();
    expect(screen.getByRole("button", { name: "Добавить изображения" })).toBeEnabled();
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
    await waitFor(() => { expect(saved).toHaveBeenCalledOnce(); });
    expect(saved.mock.lastCall?.[0].media).toEqual([
      { ...secondImage, display_order: 0, is_primary: true },
    ]);
  });

  it("reports ordering to the document owner without issuing an independent revision mutation", async () => {
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
    const altFields = screen.getAllByLabelText(/^Альтернативный текст изображения/);
    expect(altFields[0]).toHaveValue(secondImage.alt_text);
    expect(saved).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === "PUT")).toBe(false);
  });
});
