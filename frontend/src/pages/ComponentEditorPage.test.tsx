import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Category, ComponentCard, User } from "../api/contracts";
import { currentUserQueryKey } from "../auth/queries";
import { createQueryClient } from "../app/query-client";
import { routes } from "../app/routes";
import { workspaceKeys } from "../workspace/queries";

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
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
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
  it("renders a safe preview without interpreting raw HTML", async () => {
    renderEditor({ ...card, description: "<img src=x onerror=alert(1)>" });
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));

    expect(screen.getByRole("heading", { name: "Arduino Uno", level: 1 })).toBeVisible();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeVisible();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Проверить подключение питания.")).toBeVisible();
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
    const title = screen.getByLabelText("Название");
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
