import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditLogPage } from "./AuditLogPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(value: unknown): Response {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

describe("audit journal", () => {
  it("renders safe Russian events and sends exact user, action and date filters", async () => {
    const actorId = "00000000-0000-0000-0000-000000000001";
    const fetchMock = vi.fn<typeof fetch>((input) => {
      const url = requestUrl(input);
      if (url.endsWith("/api/v1/admin/users")) {
        return Promise.resolve(jsonResponse({
          items: [{
            id: actorId,
            login: "administrator",
            display_name: "Анна Администраторова",
            status: "active",
            roles: ["administrator"],
            editor_expires_at: null,
          }],
          total: 1,
        }));
      }
      if (url.includes("/api/v1/admin/audit-events")) {
        return Promise.resolve(jsonResponse({
          items: [{
            id: "00000000-0000-0000-0000-000000000002",
            occurred_at: "2026-07-29T09:00:00Z",
            actor: {
              id: actorId,
              type: "user",
              login: "administrator",
              display_name: "Анна Администраторова",
            },
            action: "component.published",
            object: {
              type: "component",
              id: "00000000-0000-0000-0000-000000000003",
            },
            outcome: "success",
          }],
          total: 1,
          limit: 50,
          offset: 0,
          available_actions: ["auth.login", "component.published"],
        }));
      }
      return Promise.reject(new Error(`Unexpected request: ${url}`));
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <AuditLogPage />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Журнал действий" })).toBeVisible();
    expect(screen.getByText("Анна Администраторова")).toBeVisible();
    expect(within(screen.getByRole("list")).getByText("Карточка опубликована")).toBeVisible();
    expect(screen.getByText(/Карточка · 00000000/)).toBeVisible();
    expect(screen.getByText("Выполнено")).toBeVisible();
    expect(screen.getByText(/доступен только для чтения/i)).toBeVisible();
    expect(screen.queryByText(/component\.published|details_safe_json|request_id/)).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Пользователь"), {
      target: { value: actorId },
    });
    fireEvent.change(screen.getByLabelText("Действие"), {
      target: { value: "component.published" },
    });
    fireEvent.change(screen.getByLabelText("Дата с"), {
      target: { value: "2026-07-01" },
    });
    fireEvent.change(screen.getByLabelText("Дата по"), {
      target: { value: "2026-07-31" },
    });

    await waitFor(() => {
      const urls = fetchMock.mock.calls.map(([input]) => requestUrl(input));
      expect(urls).toContainEqual(expect.stringContaining(`user_id=${actorId}`));
      expect(urls).toContainEqual(expect.stringContaining("action=component.published"));
      expect(urls).toContainEqual(expect.stringContaining("occurred_from="));
      expect(urls).toContainEqual(expect.stringContaining("occurred_to="));
    });
  });
});
