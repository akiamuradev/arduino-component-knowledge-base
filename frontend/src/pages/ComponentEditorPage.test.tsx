import { QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type {
  Category,
  ComponentCard,
  ComponentHistoryResponse,
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

function requestBody(options: RequestInit | undefined): string {
  if (typeof options?.body !== "string") {
    throw new Error("Expected a JSON string request body");
  }
  return options.body;
}

afterEach(() => {
  localStorage.clear();
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("component editor", () => {
  it("explains the real UNO alias duplicates inline and autosaves after correction", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async (_url, options) => {
      await Promise.resolve();
      return jsonResponse({ ...card, ...JSON.parse(requestBody(options)) as object, edit_token: 8 });
    });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();
    const aliases = screen.getByLabelText("Альтернативные имена через запятую");
    const text = "Arduino Uno Rev3, Arduino UNO Rev3, UNO R3, Arduino Uno Revision 3, A000066";
    fireEvent.change(aliases, { target: { value: text } });
    expect(aliases).toHaveValue(text);
    expect(aliases).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/«Arduino Uno Rev3» и «Arduino UNO Rev3»/)).toBeVisible();
    expect(screen.queryByText("Серверная версия карточки изменилась")).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(aliases, { target: { value: "Arduino Uno Rev3, UNO R3, Arduino Uno Revision 3, A000066" } });
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledOnce(); }, { timeout: 2000 });
    expect(aliases).toHaveAttribute("aria-invalid", "false");
  });

  it("does not revert Arduino UNO R3 when an older autosave response arrives", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    let finish!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    const fetchMock = vi.fn<typeof fetch>().mockImplementationOnce(() => pending)
      .mockImplementation(async (_url, options) => {
        await Promise.resolve();
        return jsonResponse({ ...card, ...JSON.parse(requestBody(options)) as object, edit_token: 9 });
      });
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();
    const title = within(screen.getByRole("group", { name: "Идентификация" })).getByLabelText("Название");
    fireEvent.change(title, { target: { value: "Arduino" } });
    fireEvent.keyDown(window, { key: "s", metaKey: true });
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledOnce(); });
    fireEvent.change(title, { target: { value: "Arduino UNO R3" } });
    await act(async () => { finish(jsonResponse({ ...card, title: "Arduino", edit_token: 8 })); await pending; });
    expect(title).toHaveValue("Arduino UNO R3");
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledTimes(2); });
    expect(JSON.parse(requestBody(fetchMock.mock.calls[1]?.[1]))).toEqual(expect.objectContaining({
      title: "Arduino UNO R3", edit_token: 8,
    }));
  });

  it("identifies NFKC duplicate tags without sending invalid autosaves", () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();
    const tags = screen.getByLabelText("Теги через запятую");
    fireEvent.change(tags, { target: { value: "ＵＮＯ, uno" } });
    expect(tags).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/«ＵＮＯ» и «uno»/)).toBeVisible();
    expect(fetchMock).not.toHaveBeenCalled();
  });
  it("allows images and an incomplete draft before the first save", () => {
    renderNewEditor();

    expect(screen.getByText(/Фото можно загрузить до заполнения и сохранения/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Синхронизировать сейчас" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Добавить изображения" })).toBeEnabled();
    expect(screen.getByText(/Черновик уже можно сохранить/)).toBeVisible();
  });

  it("does not create an untouched draft, then creates once after the first character", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const saved = {
      ...card,
      slug: "draft-10000000000040008000000000000000",
      title: "A",
      summary: "",
      description: "",
      revision: 1,
      media: [],
    };
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async () => {
      await Promise.resolve(); return jsonResponse(saved, 201);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderNewEditor();

    await userEvent.click(screen.getByRole("button", { name: "Синхронизировать сейчас" }));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.type(screen.getByLabelText("Название", { selector: "input" }), "A");
    fireEvent.keyDown(window, { key: "s", ctrlKey: true });
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledTimes(2); });
    const body = JSON.parse(requestBody(fetchMock.mock.calls[0]?.[1])) as {
      slug: string;
      title: string;
      summary: string;
      description: string;
      images: unknown[];
    };
    expect(body).toEqual(expect.objectContaining({
      slug: "",
      title: "A",
      summary: "",
      description: "",
    }));
  });

  it("maps two visible specification fields and omits the trailing row", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const saved = { ...card, revision: 1, specifications: [] };
    const fetchMock = vi.fn<typeof fetch>().mockImplementation(async () => {
      await Promise.resolve(); return jsonResponse(saved, 201);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderNewEditor();

    await userEvent.type(screen.getByLabelText("Характеристика 1"), "Напряжение питания");
    await userEvent.type(screen.getByLabelText("Значение характеристики 1"), "5 В");
    await userEvent.click(screen.getByRole("button", { name: "Синхронизировать сейчас" }));

    const body = JSON.parse(requestBody(fetchMock.mock.calls[0]?.[1])) as {
      specifications: unknown[];
    };
    expect(body.specifications).toEqual([{
      key: "napryazhenie-pitaniya",
      label: "Напряжение питания",
      value_text: "5 В",
      value_number: "5",
      unit: "В",
    }]);
  });

  it("preserves an untouched existing specification when saving", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({
      ...card, revision: 8,
    }));
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    expect(screen.getByLabelText("Характеристика 1")).toHaveValue("Частота");
    expect(screen.getByLabelText("Значение характеристики 1")).toHaveValue("16");
    expect(screen.queryByLabelText("Ключ")).not.toBeInTheDocument();
    await userEvent.type(within(screen.getByRole("group", { name: "Идентификация" })).getByLabelText("Название"), " ");
    await userEvent.click(screen.getByRole("button", { name: "Синхронизировать сейчас" }));

    const body = JSON.parse(requestBody(fetchMock.mock.calls[0]?.[1])) as {
      specifications: unknown[];
    };
    expect(body.specifications).toEqual([{
      key: "clock-frequency",
      label: "Частота",
      value_text: "16",
      value_number: "16",
      unit: "МГц",
    }]);
  });

  it("does not submit a half-filled specification", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);
    renderNewEditor();
    await userEvent.type(screen.getByLabelText("Значение характеристики 1"), "5 В");

    await userEvent.click(screen.getByRole("button", { name: "Синхронизировать сейчас" }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByText("Укажите название характеристики.")).toBeVisible();
    expect(screen.getByLabelText("Характеристика 1")).toHaveFocus();
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
    await userEvent.click(screen.getByRole("tab", { name: "Предпросмотр" }));

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
    await userEvent.click(screen.getByRole("tab", { name: "Предпросмотр" }));

    const gallery = await screen.findByRole("region", {
      name: "Галерея изображений компонента",
    });
    expect(screen.getByRole("img", { name: "Основной вид редактора" })).toBeVisible();
    expect(screen.getByText("Основной кадр")).toBeVisible();
    expect(gallery).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Следующее изображение" }));
    expect(screen.getByRole("img", { name: "Разъёмы редактора" })).toBeVisible();
  });

  it("shows safe Russian authorship history without revision payloads", async () => {
    const history: ComponentHistoryResponse = {
      items: [
        {
          revision: 8,
          previous_status: "draft",
          status: "in_review",
          summary: "Карточка отправлена на проверку",
          actor_display_name: "Редактор",
          occurred_at: "2026-07-28T10:00:00Z",
        },
        {
          revision: 7,
          previous_status: null,
          status: "draft",
          summary: "Карточка создана",
          actor_display_name: "Редактор",
          occurred_at: "2026-07-28T09:00:00Z",
        },
      ],
      total: 2,
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(history));
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    await userEvent.click(screen.getByRole("tab", { name: "История" }));

    const region = await screen.findByRole("region", {
      name: "История изменений карточки",
    });
    expect(within(region).getByText("Карточка отправлена на проверку")).toBeVisible();
    expect(within(region).getByText("Черновик → На проверке")).toBeVisible();
    expect(within(region).getAllByText("Редактор")).toHaveLength(2);
    expect(within(region).getByText("2 записи")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.stringify(history)).not.toContain("content_json");
    expect(JSON.stringify(history)).not.toContain("teacher_notes");
  });

  it("shows teacher correction proposals in a separate review tab", async () => {
    const proposals = {
      items: [
        {
          id: "00000000-0000-0000-0000-000000000099",
          component_id: card.id,
          author_display_name: "Преподаватель",
          message: "Уточнить максимально допустимое напряжение питания.",
          status: "open",
          created_at: "2026-07-29T12:00:00Z",
          resolved_at: null,
        },
      ],
      total: 1,
    };
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(proposals));
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    await userEvent.click(screen.getByRole("tab", { name: "Предложения" }));

    const region = await screen.findByRole("region", {
      name: "Предложения исправлений",
    });
    expect(within(region).getByText("Преподаватель")).toBeVisible();
    expect(
      within(region).getByText("Уточнить максимально допустимое напряжение питания."),
    ).toBeVisible();
    expect(within(region).getByRole("button", { name: "Отметить учтённым" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledOnce();
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
    await userEvent.click(screen.getByRole("button", { name: "Синхронизировать сейчас" }));

    expect(await screen.findByText("Серверная версия карточки изменилась")).toBeVisible();
    expect(title).toHaveValue("Локальное название");
    expect(screen.getByRole("button", { name: "Загрузить версию с сервера" })).toBeVisible();
  });

  it("runs review, publication, visibility and reversible archive transitions", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const inReview = { ...card, status: "in_review" as const, revision: 8 };
    const changesRequested = { ...card, status: "changes_requested" as const, revision: 9 };
    const resubmitted = { ...card, status: "in_review" as const, revision: 10 };
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
      .mockResolvedValueOnce(jsonResponse(published))
      .mockResolvedValueOnce(jsonResponse(hidden))
      .mockResolvedValueOnce(jsonResponse(shown))
      .mockResolvedValueOnce(jsonResponse(archived));
    fetchMock.mockResolvedValueOnce(jsonResponse(restored));
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    await userEvent.click(screen.getByRole("button", { name: "Отправить на проверку" }));
    await userEvent.click(await screen.findByRole("button", { name: "Вернуть на доработку" }));
    await userEvent.click(await screen.findByRole("button", { name: "Отправить на проверку" }));
    await userEvent.click(await screen.findByRole("button", { name: "Одобрить и опубликовать" }));
    await userEvent.click(await screen.findByRole("button", { name: "Скрыть" }));
    await userEvent.click(await screen.findByRole("button", { name: "Вернуть в каталог" }));
    await userEvent.click(await screen.findByRole("button", { name: "В архив" }));
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));
    await userEvent.click(await screen.findByRole("button", { name: "Восстановить из архива" }));

    expect(await screen.findByRole("button", { name: "Скрыть" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(8);
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe('{"edit_token":7}');
    expect(fetchMock.mock.calls[7]?.[1]?.body).toBe('{"edit_token":15}');
  });

  it("lets an editor submit but not review or publish", () => {
    renderEditor(card, editor);

    expect(screen.queryByRole("button", { name: "Опубликовать" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Одобрить" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отправить на проверку" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Синхронизировать сейчас" })).toBeEnabled();
  });
});
