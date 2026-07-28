import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  Category,
  ComponentCard,
  ComponentMedia,
  User,
} from "../api/contracts";
import { currentUserQueryKey } from "../auth/queries";
import { createQueryClient } from "../app/query-client";
import { routes } from "../app/routes";
import { workspaceKeys } from "../workspace/queries";
import { ThemeProvider } from "../theme/ThemeProvider";

const administrator: User = {
  id: "00000000-0000-0000-0000-000000000010",
  login: "administrator",
  display_name: "Администратор",
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

const editor: User = {
  ...administrator,
  login: "editor",
  display_name: "Редактор",
  roles: ["student", "editor"],
  permissions: [
    "components.view",
    "components.create",
    "components.edit",
    "components.archive",
    "components.submit_for_review",
  ],
};

const category: Category = {
  id: "00000000-0000-0000-0000-000000000020",
  slug: "boards",
  name: "Платы",
};

const card: ComponentCard = {
  id: "00000000-0000-0000-0000-000000000030",
  slug: "arduino-uno",
  status: "draft",
  title: "Arduino Uno",
  aliases: ["Uno R3"],
  manufacturer: "Arduino",
  model: "A000066",
  primary_category: category,
  primary_category_id: category.id,
  tags: ["avr", "учебная"],
  summary: "Учебная плата на базе микроконтроллера ATmega328P.",
  description: "Безопасное текстовое описание платы.",
  purpose: "Прототипирование",
  usage_notes: null,
  safety_notes: "Не превышать допустимое напряжение.",
  difficulty: "beginner",
  teacher_notes: "Проверить подключение питания.",
  manual_original: true,
  published_at: null,
  archived_from_status: null,
  revision: 7,
  updated_at: "2026-07-15T20:00:00Z",
  sources: [],
  specifications: [{ key: "clock-frequency", label: "Частота", value_text: "16", value_number: "16", unit: "МГц", position: 0 }],
  compatibility: [{ target_type: "board", name: "Arduino Uno", version_constraint: "R3", notes: null, position: 0 }],
  code_examples: [{
    title: "Blink", language: "arduino", practical_task: "Заставьте светодиод мигать.",
    hints: ["Настройте пин как выход."], body: "void loop() { digitalWrite(13, HIGH); }",
    libraries: [], explanation: "HIGH включает светодиод.", visibility: "student", position: 0,
  }],
};

const editorImages: ComponentMedia[] = [
  {
    asset_id: "10000000-0000-4000-8000-000000000001",
    kind: "image",
    purpose: "detail",
    alt_text: "Разъёмы редактора",
    caption: "Детальный вид",
    display_order: 0,
    is_primary: false,
    status: "ready",
    width: 800,
    height: 600,
    variants: [{
      name: "320w", mime: "image/webp", width: 320, height: 240,
      sha256: "1".repeat(64),
    }],
  },
  {
    asset_id: "10000000-0000-4000-8000-000000000002",
    kind: "image",
    purpose: "product",
    alt_text: "Основной вид редактора",
    caption: "Основной кадр",
    display_order: 1,
    is_primary: true,
    status: "ready",
    width: 1600,
    height: 1200,
    variants: [{
      name: "320w", mime: "image/webp", width: 320, height: 240,
      sha256: "2".repeat(64),
    }],
  },
];

function renderEditor(component: ComponentCard = card, user: User = administrator) {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  queryClient.setQueryData(currentUserQueryKey, user);
  queryClient.setQueryData(workspaceKeys.categories, [category]);
  queryClient.setQueryData(workspaceKeys.component(component.id), component);
  const router = createMemoryRouter(routes, {
    initialEntries: [`/admin/components/${component.id}/edit`],
  });
  render(
    <ThemeProvider><QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider></ThemeProvider>,
  );
}

function renderNewEditor() {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  queryClient.setQueryData(currentUserQueryKey, administrator);
  queryClient.setQueryData(workspaceKeys.categories, [category]);
  const router = createMemoryRouter(routes, {
    initialEntries: ["/admin/components/new"],
  });
  render(
    <ThemeProvider><QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider></ThemeProvider>,
  );
}

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("component editor", () => {
  it("allows a new draft without images and explains when upload becomes available", () => {
    renderNewEditor();

    expect(screen.getByText("Сначала сохраните draft")).toBeVisible();
    expect(screen.getByText(/Карточку можно сохранить без изображений/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Сохранить draft" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Добавить изображения" })).not.toBeInTheDocument();
  });

  it("places the persistent image editor between identification and learning content", () => {
    renderEditor();

    const identification = screen.getByRole("group", { name: "Идентификация" });
    const images = screen.getByRole("group", { name: "Изображения" });
    const learning = screen.getByRole("group", { name: "Учебное содержание" });

    expect(
      identification.compareDocumentPosition(images)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      images.compareDocumentPosition(learning)
      & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Добавить изображения" })).toBeEnabled();
  });

  it("warns an editor when imported content has an unknown license", async () => {
    renderEditor({
      ...card,
      manual_original: false,
      sources: [{
        display_name: "Unverified source", original_url: "https://example.com/item",
        repository_url: null, license_name: "Unknown", license_spdx: "Unknown",
        license_url: "https://example.com/license", source_revision: "1234567890abcdef",
        source_tag: null, source_file_path: "item.md", source_entry_name: null,
        modifications_notice: "Imported without modification details.", imported_at: "2026-07-15T10:00:00Z",
        attribution: "Unverified source", parser_name: "legacy", parser_version: "1.0.0",
      }],
    });
    expect(await screen.findByText(/Условия использования материала не определены/)).toBeVisible();
  });

  it("renders a safe preview without interpreting raw HTML", async () => {
    renderEditor({ ...card, description: "<img src=x onerror=alert(1)>" });
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(screen.getByRole("heading", { name: "Arduino Uno", level: 1 })).toBeVisible();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Проверить подключение питания.")).toBeVisible();
    expect(screen.getByText("Частота")).toBeVisible();
    expect(screen.getByText("16 МГц")).toBeVisible();
    expect(screen.getByText("Arduino Uno", { selector: "strong" })).toBeVisible();
  });

  it("renders editor image state as a primary-first preview gallery", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation((input) => {
        const url = typeof input === "string"
          ? input
          : input instanceof URL
            ? input.toString()
            : input.url;
        const image = editorImages.find((item) => url.includes(item.asset_id));
        if (image === undefined) throw new Error(`Unexpected request: ${url}`);
        return Promise.resolve(jsonResponse({
          status: "ready",
          variants: image.variants.map((variant) => ({
            ...variant,
            url: `/media-storage/${image.asset_id}/${variant.name}.webp?signed=1`,
          })),
        }));
      }),
    );
    renderEditor({ ...card, media: editorImages });
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    const gallery = await screen.findByRole("region", {
      name: "Галерея изображений компонента",
    });
    expect(screen.getByRole("img", { name: "Основной вид редактора" })).toBeVisible();
    expect(screen.getByText("Основной кадр")).toBeVisible();
    expect(gallery).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Следующее изображение" }));
    expect(screen.getByRole("img", { name: "Разъёмы редактора" })).toBeVisible();
  });

  it("keeps local edits and stops a blind overwrite on revision conflict", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        jsonResponse({ detail: { code: "revision_conflict", current_revision: 8 } }, 409),
      ),
    );
    renderEditor();
    const title = within(screen.getByRole("group", { name: "Идентификация" })).getByLabelText("Название");
    await userEvent.clear(title);
    await userEvent.type(title, "Локальное название");
    await userEvent.click(screen.getByRole("button", { name: "Сохранить draft" }));

    expect(await screen.findByText("Карточку уже изменил другой пользователь")).toBeVisible();
    expect(title).toHaveValue("Локальное название");
    expect(screen.getByRole("button", { name: "Загрузить серверную revision" })).toBeVisible();
  });

  it("runs review, publication, visibility and reversible archive transitions", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const inReview = { ...card, status: "in_review" as const, revision: 8 };
    const changesRequested = { ...card, status: "changes_requested" as const, revision: 9 };
    const resubmitted = { ...card, status: "in_review" as const, revision: 10 };
    const approved = { ...card, status: "approved" as const, revision: 11 };
    const published = { ...card, status: "published" as const, revision: 12, published_at: "2026-07-15T21:00:00Z" };
    const hidden = { ...published, status: "hidden" as const, revision: 13 };
    const shown = { ...published, revision: 14 };
    const archived = { ...shown, status: "archived" as const, revision: 15, archived_from_status: "published" as const };
    const restored = { ...shown, revision: 16 };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(inReview))
      .mockResolvedValueOnce(jsonResponse(changesRequested))
      .mockResolvedValueOnce(jsonResponse(resubmitted))
      .mockResolvedValueOnce(jsonResponse(approved))
      .mockResolvedValueOnce(jsonResponse(published))
      .mockResolvedValueOnce(jsonResponse(hidden))
      .mockResolvedValueOnce(jsonResponse(shown))
      .mockResolvedValueOnce(jsonResponse(archived));
    fetchMock.mockResolvedValueOnce(jsonResponse(restored));
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    await userEvent.click(screen.getByRole("button", { name: "Отправить на проверку" }));
    await userEvent.click(await screen.findByRole("button", { name: "Запросить исправления" }));
    await userEvent.click(await screen.findByRole("button", { name: "Отправить на проверку" }));
    await userEvent.click(await screen.findByRole("button", { name: "Одобрить" }));
    await userEvent.click(await screen.findByRole("button", { name: "Опубликовать" }));
    await userEvent.click(await screen.findByRole("button", { name: "Скрыть" }));
    await userEvent.click(await screen.findByRole("button", { name: "Вернуть в каталог" }));
    await userEvent.click(await screen.findByRole("button", { name: "В архив" }));
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await userEvent.click(await screen.findByRole("button", { name: "Восстановить из архива" }));

    expect(await screen.findByText("Revision 16")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(9);
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe('{"revision":7}');
    expect(fetchMock.mock.calls[8]?.[1]?.body).toBe('{"revision":15}');
  });

  it("lets an editor submit but not review or publish", () => {
    renderEditor(card, editor);

    expect(screen.queryByRole("button", { name: "Опубликовать" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Одобрить" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить на проверку" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Сохранить draft" })).toBeEnabled();
  });
});
