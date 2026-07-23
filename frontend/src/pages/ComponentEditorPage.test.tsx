import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Category, ComponentCard, User } from "../api/contracts";
import { currentUserQueryKey } from "../auth/queries";
import { createQueryClient } from "../app/query-client";
import { routes } from "../app/routes";
import { workspaceKeys } from "../workspace/queries";
import { ThemeProvider } from "../theme/ThemeProvider";

const teacher: User = {
  id: "00000000-0000-0000-0000-000000000010",
  login: "teacher",
  display_name: "Преподаватель",
  roles: ["teacher"],
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

function renderEditor(component: ComponentCard = card) {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  queryClient.setQueryData(currentUserQueryKey, teacher);
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
  queryClient.setQueryData(currentUserQueryKey, teacher);
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

  it("publishes and archives with the current optimistic revision", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const published = { ...card, status: "published" as const, revision: 8, published_at: "2026-07-15T21:00:00Z" };
    const archived = { ...published, status: "archived" as const, revision: 9 };
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(jsonResponse(published))
      .mockResolvedValueOnce(jsonResponse(archived));
    vi.stubGlobal("fetch", fetchMock);
    renderEditor();

    await userEvent.click(screen.getByRole("button", { name: "Опубликовать" }));
    await userEvent.click(await screen.findByRole("button", { name: "В архив" }));
    await userEvent.click(screen.getByRole("button", { name: "Подтвердить" }));

    expect(await screen.findByText("Revision 9")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe('{"revision":7}');
    expect(fetchMock.mock.calls[1]?.[1]?.body).toBe('{"revision":8}');
  });
});
