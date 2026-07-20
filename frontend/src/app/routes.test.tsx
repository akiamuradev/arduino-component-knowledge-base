import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { User } from "../api/contracts";
import { currentUserQueryKey } from "../auth/queries";
import { catalogKeys } from "../catalog/queries";
import { duplicateKeys } from "../duplicates/queries";
import { jobKeys } from "../jobs/queries";
import { workspaceKeys } from "../workspace/queries";
import { ThemeProvider } from "../theme/ThemeProvider";
import { createQueryClient } from "./query-client";
import { routes } from "./routes";

const student: User = {
  id: "00000000-0000-0000-0000-000000000001",
  login: "student",
  display_name: "Студент",
  roles: ["student"],
};

function renderRoute(path: string, user: User) {
  const queryClient = createQueryClient();
  queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
  queryClient.setQueryData(currentUserQueryKey, user);
  queryClient.setQueryData(workspaceKeys.components(), { items: [], total: 0 });
  queryClient.setQueryData(catalogKeys.categories, []);
  queryClient.setQueryData(catalogKeys.sources, []);
  queryClient.setQueryData(
    catalogKeys.list({ query: "", categoryId: "", difficulty: "" }),
    { items: [], total: 0 },
  );
  queryClient.setQueryData(jobKeys.list(), {
    items: [
      {
        id: "00000000-0000-0000-0000-000000000010",
        asset_id: "00000000-0000-0000-0000-000000000011",
        owner_user_id: student.id,
        kind: "video",
        queue_name: "videos",
        task_name: "process_media_video",
        status: "failed",
        phase: "failed",
        progress_percent: 55,
        attempts: 4,
        max_attempts: 4,
        manual_retry_count: 0,
        error_code: "media_storage_failed",
        next_retry_at: null,
        heartbeat_at: null,
        last_enqueued_at: null,
        created_at: "2026-07-15T12:00:00Z",
        started_at: "2026-07-15T12:00:01Z",
        finished_at: "2026-07-15T12:00:20Z",
        updated_at: "2026-07-15T12:00:20Z",
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  });
  queryClient.setQueryData(jobKeys.imports(), {
    items: [
      {
        id: "00000000-0000-0000-0000-000000000020",
        requested_by: student.id,
        status: "failed",
        attempts: 1,
        max_attempts: 4,
        error_code: "catalog_conflict",
        next_retry_at: null,
        heartbeat_at: "2026-07-15T12:00:20Z",
        created_at: "2026-07-15T12:00:00Z",
        started_at: "2026-07-15T12:00:01Z",
        finished_at: "2026-07-15T12:00:20Z",
        updated_at: "2026-07-15T12:00:20Z",
        repository_url: "https://github.com/Seeed-Studio/wiki-documents",
        source_file_path: "sites/en/docs/Sensor/Grove/Grove-Button.md",
        source_entry_name: null,
        draft_component_id: null,
        retryable: true,
      },
    ],
    total: 1,
    limit: 50,
    offset: 0,
  });
  queryClient.setQueryData(duplicateKeys.all, { items: [], total: 0 });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return render(
    <ThemeProvider><QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider></ThemeProvider>,
  );
}

describe("application routes", () => {
  it("renders the student layout and empty search result", async () => {
    renderRoute("/", student);
    expect(await screen.findByRole("heading", { name: "Исследуйте мир Arduino-компонентов" })).toBeVisible();
    expect(screen.getByText("Ничего не найдено")).toBeVisible();
    expect(screen.queryByRole("link", { name: /Добавить компонент/ })).not.toBeInTheDocument();
  });

  it("does not expose the admin layout to a student", async () => {
    renderRoute("/admin", student);
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Обзор системы" })).not.toBeInTheDocument();
  });

  it("renders the workspace for a backend-provided administrator role", async () => {
    renderRoute("/admin", { ...student, roles: ["administrator"] });
    expect(await screen.findByRole("heading", { name: "Редакция" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Обзор материалов" })).toBeVisible();
    expect(screen.getByText("Права проверяются сервером")).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Новая карточка" })[0]).toHaveAttribute("href", "/admin/components/new");
  });

  it("allows a teacher into the editorial workspace", async () => {
    renderRoute("/admin", { ...student, roles: ["teacher"] });
    expect(await screen.findByRole("heading", { name: "Редакция" })).toBeVisible();
  });

  it("renders durable jobs only for an administrator", async () => {
    renderRoute("/admin/jobs", { ...student, roles: ["administrator"] });
    expect(await screen.findByRole("heading", { name: "Фоновые задачи" })).toBeVisible();
    expect(screen.getByText("process_media_video")).toBeVisible();
    expect(screen.getByText("media_storage_failed")).toBeVisible();
    expect(screen.getByText(/Grove-Button\.md/)).toBeVisible();
    expect(screen.getByText("catalog_conflict")).toBeVisible();
    expect(screen.getAllByRole("button", { name: "Повторить" })).toHaveLength(2);
  });

  it("does not expose the job monitor to a teacher", async () => {
    renderRoute("/admin/jobs", { ...student, roles: ["teacher"] });
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeVisible();
    expect(screen.queryByText("process_media_video")).not.toBeInTheDocument();
  });

  it("renders duplicate review only for an administrator", async () => {
    renderRoute("/admin/duplicates", { ...student, roles: ["administrator"] });
    expect(await screen.findByRole("heading", { name: "Проверка дубликатов" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Дубликатов не найдено" })).toBeVisible();
  });

  it("does not expose duplicate decisions to a teacher", async () => {
    renderRoute("/admin/duplicates", { ...student, roles: ["teacher"] });
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Проверка дубликатов" })).not.toBeInTheDocument();
  });

  it("renders the source registry for authenticated students", async () => {
    renderRoute("/sources", student);
    expect(await screen.findByRole("heading", { name: "Источники и лицензии" })).toBeVisible();
  });

  it("exposes repository import only to an administrator", async () => {
    const view = renderRoute("/admin/import", { ...student, roles: ["administrator"] });
    expect(await screen.findByRole("heading", { name: "Импорт из Git-источника" })).toBeVisible();
    view.unmount();
    renderRoute("/admin/import", { ...student, roles: ["teacher"] });
    expect(await screen.findByRole("heading", { name: "Недостаточно прав" })).toBeVisible();
  });
});
