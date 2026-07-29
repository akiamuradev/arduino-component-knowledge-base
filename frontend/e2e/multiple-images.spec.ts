import { expect, type Route, test } from "@playwright/test";

const administrator = {
  id: "10000000-0000-4000-8000-000000000001",
  login: "administrator",
  display_name: "Integration Administrator",
  roles: ["administrator"],
  permissions: [
    "components.view",
    "components.create",
    "components.edit",
    "components.archive",
    "components.submit_for_review",
    "components.review",
    "components.publish",
  ],
};
const category = {
  id: "20000000-0000-4000-8000-000000000001",
  slug: "sensors",
  name: "Датчики",
};
const componentId = "30000000-0000-4000-8000-000000000001";
const assetIds = [
  "40000000-0000-4000-8000-000000000001",
  "40000000-0000-4000-8000-000000000002",
];

interface TestMedia {
  asset_id: string;
  kind: "image";
  purpose: string;
  alt_text: string;
  caption: string | null;
  display_order: number;
  is_primary: boolean;
  status: "pending" | "ready";
  width: number | null;
  height: number | null;
  variants: {
    name: string;
    mime: string;
    width: number;
    height: number;
    sha256: string;
  }[];
}

interface CreatePayload {
  images: Pick<TestMedia, "asset_id" | "purpose" | "alt_text" | "caption">[];
  primary_asset_id: string | null;
}

test("multiple-image draft, upload, publication and immutable public snapshot", async ({
  context,
  page,
}) => {
  await context.addCookies([{
    name: "ackb_csrf",
    value: "e2e-csrf",
    url: "http://127.0.0.1:4173",
  }]);
  let revision = 0;
  let status: "draft" | "in_review" | "approved" | "published" = "draft";
  let publishedAt: string | null = null;
  let liveMedia: TestMedia[] = [];
  let publishedMedia: TestMedia[] = [];
  let publicPayload = "";
  let draftCreated = false;
  let createPayload: CreatePayload | null = null;

  const workspaceCard = () => ({
    id: componentId,
    slug: "multi-image-sensor",
    status,
    title: "Датчик с двумя изображениями",
    aliases: [],
    manufacturer: null,
    model: null,
    primary_category: category,
    primary_category_id: category.id,
    tags: [],
    summary: "Учебная карточка с несколькими изображениями компонента.",
    description: "Описание компонента для полного E2E-сценария публикации.",
    purpose: null,
    usage_notes: null,
    safety_notes: null,
    difficulty: "beginner",
    teacher_notes: null,
    manual_original: true,
    published_at: publishedAt,
    archived_from_status: null,
    revision,
    updated_at: "2026-07-27T13:00:00Z",
    sources: [],
    specifications: [],
    compatibility: [],
    code_examples: [],
    media: liveMedia,
  });
  const mediaAsset = (item: TestMedia) => ({
    id: item.asset_id,
    kind: item.kind,
    component_id: draftCreated ? componentId : null,
    purpose: item.purpose,
    alt_text: item.alt_text,
    caption: item.caption,
    display_order: item.display_order,
    is_primary: item.is_primary,
    status: item.status,
    declared_mime: "image/png",
    detected_mime: item.status === "ready" ? "image/png" : null,
    size_bytes: item.status === "ready" ? 128 : null,
    sha256: item.status === "ready" ? "a".repeat(64) : null,
    phash: item.status === "ready" ? "b".repeat(16) : null,
    width: item.width,
    height: item.height,
    duration_ms: null,
    video_codec: null,
    audio_codec: null,
    frame_rate: null,
    failure_code: null,
    job_status: item.status === "ready" ? "succeeded" : "queued",
    phase: item.status === "ready" ? "completed" : "queued",
    progress_percent: item.status === "ready" ? 100 : 0,
    variants: item.status === "ready"
      ? item.variants.map((variant) => ({
          ...variant,
          size_bytes: 96,
          duration_ms: null,
          video_codec: null,
          audio_codec: null,
          frame_rate: null,
          url: `/media-storage/variants/${item.asset_id}.svg?signed=editor`,
        }))
      : [],
  });
  const publicCard = () => {
    const body = {
      id: componentId,
      slug: "multi-image-sensor",
      title: "Датчик с двумя изображениями",
      summary: "Учебная карточка с несколькими изображениями компонента.",
      primary_category: category,
      aliases: [],
      manufacturer: null,
      model: null,
      tags: [],
      description: "Описание компонента для полного E2E-сценария публикации.",
      purpose: null,
      usage_notes: null,
      safety_notes: null,
      difficulty: "beginner",
      published_at: publishedAt,
      specifications: [],
      compatibility: [],
      code_examples: [],
      sources: [],
      media: publishedMedia.map((item) => ({
        asset_id: item.asset_id,
        kind: item.kind,
        purpose: item.purpose,
        alt_text: item.alt_text,
        caption: item.caption,
        display_order: item.display_order,
        is_primary: item.is_primary,
        width: item.width,
        height: item.height,
        variants: item.variants.map((variant) => ({
          ...variant,
          url: `/media-storage/variants/${item.asset_id}.svg?signed=public`,
        })),
      })),
    };
    publicPayload = JSON.stringify(body);
    return body;
  };
  const json = async (route: Route, body: unknown, responseStatus = 200) => {
    await route.fulfill({
      status: responseStatus,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  };

  await page.route("**/media-storage/**", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({ status: 200, body: "" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"320\" height=\"240\"><rect width=\"320\" height=\"240\" fill=\"#168e52\"/></svg>",
    });
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/me") return json(route, administrator);
    if (path === "/api/v1/workspace/categories") return json(route, [category]);
    if (path === "/api/v1/catalog/categories") return json(route, [category]);
    if (path === "/api/v1/workspace/components" && request.method() === "POST") {
      createPayload = request.postDataJSON() as CreatePayload;
      draftCreated = true;
      revision = 1;
      status = "draft";
      return json(route, workspaceCard(), 201);
    }
    if (path === `/api/v1/workspace/components/${componentId}`) {
      return json(route, workspaceCard());
    }
    if (path === "/api/v1/media/images/uploads" && request.method() === "POST") {
      const payload = request.postDataJSON() as {
        alt_text: string;
        purpose: string;
        component_id: string | null;
        component_revision: number | null;
      };
      const assetId = assetIds[liveMedia.length];
      liveMedia.push({
        asset_id: assetId,
        kind: "image",
        purpose: payload.purpose,
        alt_text: payload.alt_text,
        caption: null,
        display_order: liveMedia.length,
        is_primary: liveMedia.length === 0,
        status: "pending",
        width: null,
        height: null,
        variants: [],
      });
      const attached = payload.component_id !== null;
      if (attached) revision += 1;
      return json(route, {
        asset_id: assetId,
        upload_url: `/media-storage/quarantine/${assetId}?signed=upload`,
        upload_headers: { "Content-Type": "image/png" },
        expires_at: "2026-07-27T14:00:00Z",
        component_revision: attached ? revision : null,
      }, 201);
    }
    const complete = /^\/api\/v1\/media\/images\/([^/]+)\/complete$/.exec(path);
    if (complete !== null && request.method() === "POST") {
      const item = liveMedia.find((candidate) => candidate.asset_id === complete[1]);
      if (item === undefined) throw new Error("Unknown completed image");
      item.status = "ready";
      item.width = 640;
      item.height = 480;
      item.variants = [{
        name: "320w",
        mime: "image/webp",
        width: 320,
        height: 240,
        sha256: item.asset_id.endsWith("1") ? "1".repeat(64) : "2".repeat(64),
      }];
      return json(route, {
        asset_id: item.asset_id,
        job_id: `job-${item.asset_id}`,
        status: "queued",
      });
    }
    const imageStatus = /^\/api\/v1\/media\/images\/([^/]+)$/.exec(path);
    if (imageStatus !== null) {
      const item = liveMedia.find((candidate) => candidate.asset_id === imageStatus[1]);
      if (item === undefined) return json(route, { detail: { code: "media_not_found" } }, 404);
      return json(route, mediaAsset(item));
    }
    if (
      path === `/api/v1/workspace/components/${componentId}/images`
      && request.method() === "PUT"
    ) {
      const payload = request.postDataJSON() as {
        images: Pick<TestMedia, "asset_id" | "purpose" | "alt_text" | "caption">[];
        primary_asset_id: string;
      };
      const byId = new Map(liveMedia.map((item) => [item.asset_id, item]));
      liveMedia = payload.images.map((item, index) => {
        const existing = byId.get(item.asset_id);
        if (existing === undefined) throw new Error("Unknown image mutation");
        return {
          ...existing,
          ...item,
          display_order: index,
          is_primary: item.asset_id === payload.primary_asset_id,
        };
      });
      revision += 1;
      status = "draft";
      return json(route, workspaceCard());
    }
    if (
      path === `/api/v1/workspace/components/${componentId}/submit-for-review`
      && request.method() === "POST"
    ) {
      revision += 1;
      status = "in_review";
      return json(route, workspaceCard());
    }
    if (
      path === `/api/v1/workspace/components/${componentId}/approve`
      && request.method() === "POST"
    ) {
      revision += 1;
      status = "approved";
      return json(route, workspaceCard());
    }
    if (
      path === `/api/v1/workspace/components/${componentId}/publish`
      && request.method() === "POST"
    ) {
      publishedMedia = structuredClone(liveMedia);
      revision += 1;
      status = "published";
      publishedAt = "2026-07-27T13:30:00Z";
      return json(route, workspaceCard());
    }
    if (path === "/api/v1/catalog/components/multi-image-sensor") {
      return json(route, publicCard());
    }
    await json(route, { detail: { code: "unexpected_e2e_request", path } }, 500);
  });

  await page.goto("/admin/components/new");
  await page.getByLabel("Добавить изображения").setInputFiles([
    { name: "front.png", mimeType: "image/png", buffer: Buffer.from("front") },
    { name: "back.png", mimeType: "image/png", buffer: Buffer.from("back") },
  ]);
  await expect(page.getByText("2 / 12")).toBeVisible();
  await expect(page.getByText("Готово")).toHaveCount(2);
  await expect(page.getByText(/Фото уже загружены/)).toBeVisible();

  await page.getByLabel("Название", { exact: true }).fill("Датчик с двумя изображениями");
  await page.getByLabel("Адрес страницы").fill("multi-image-sensor");
  await page.getByLabel("Аннотация").fill(
    "Учебная карточка с несколькими изображениями компонента.",
  );
  await page.getByLabel("Описание (Markdown без необработанного HTML)").fill(
    "Описание компонента для полного E2E-сценария публикации.",
  );
  await page.getByRole("button", { name: "Сохранить черновик" }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/components/${componentId}/edit$`));
  const submittedCreatePayload = createPayload as CreatePayload | null;
  expect(submittedCreatePayload).not.toBeNull();
  if (submittedCreatePayload === null) throw new Error("Draft creation was not requested");
  expect(submittedCreatePayload.images.map((item) => item.asset_id)).toEqual(assetIds);
  expect(submittedCreatePayload.primary_asset_id).toBe(assetIds[0]);
  await page.getByLabel("Альтернативный текст изображения 1").fill("Вид спереди");
  await page.getByLabel("Подпись изображения 1").fill("Передняя сторона");
  await page.getByLabel("Альтернативный текст изображения 2").fill("Вид сзади");
  await page.getByLabel("Подпись изображения 2").fill("Задняя сторона");
  await page.getByLabel("Основное изображение 2").check();
  await page.getByRole("button", { name: "Переместить изображение 2 выше" }).click();
  await page.getByRole("button", { name: "Сохранить изображения" }).click();
  await expect(page.getByText("Версия 2")).toBeVisible();
  await page.getByRole("button", { name: "Отправить на проверку" }).click();
  await expect(page.getByText("Версия 3")).toBeVisible();
  await page.getByRole("button", { name: "Одобрить" }).click();
  await expect(page.getByText("Версия 4")).toBeVisible();
  await page.getByRole("button", { name: "Опубликовать" }).click();
  await expect(page.getByText("Версия 5")).toBeVisible();

  await page.goto("/components/multi-image-sensor");
  await expect(page.getByRole("img", { name: "Вид сзади" })).toBeVisible();
  await expect(page.getByText("Задняя сторона")).toBeVisible();
  expect(publicPayload).not.toContain("original_url");
  expect(publicPayload).not.toContain("object_key");
  expect(publicPayload).not.toContain("quarantine");
  const publishedOrder = publishedMedia.map((item) => item.asset_id);

  await page.goto(`/admin/components/${componentId}/edit`);
  await page.getByRole("button", { name: "Переместить изображение 2 выше" }).click();
  await page.getByRole("button", { name: "Сохранить изображения" }).click();
  await expect(page.getByText("Версия 6")).toBeVisible();
  expect(liveMedia.map((item) => item.asset_id)).not.toEqual(publishedOrder);

  await page.goto("/components/multi-image-sensor");
  await expect(page.getByRole("img", { name: "Вид сзади" })).toBeVisible();
  expect(publishedMedia.map((item) => item.asset_id)).toEqual(publishedOrder);
});
