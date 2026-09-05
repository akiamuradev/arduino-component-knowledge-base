import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ManagedUserListResponse } from "../api/contracts";
import { createQueryClient } from "../app/query-client";
import { UserManagementPage } from "./UserManagementPage";

function jsonResponse(value: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(value), {
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  return input instanceof URL ? input.href : input.url;
}

function articleFor(name: string): HTMLElement {
  const article = screen.getByText(name).closest("article");
  if (!(article instanceof HTMLElement)) {
    throw new Error(`Article not found for ${name}`);
  }
  return article;
}

function callBody(
  call: [input: RequestInfo | URL, init?: RequestInit] | undefined,
): string {
  const body = call?.[1]?.body;
  if (typeof body !== "string") {
    throw new Error("Expected a JSON string request body");
  }
  return body;
}

function managedUsers(editorActive = true): ManagedUserListResponse {
  return {
    items: [
      {
        id: "00000000-0000-0000-0000-000000000001",
        login: "administrator",
        display_name: "Главный администратор",
        status: "active",
        roles: ["administrator"],
        editor_expires_at: null,
      },
      {
        id: "00000000-0000-0000-0000-000000000002",
        login: "editor",
        display_name: "Активный редактор",
        status: "active",
        roles: editorActive ? ["student", "editor"] : ["student"],
        editor_expires_at: editorActive ? "2099-08-04T10:00:00Z" : null,
      },
      {
        id: "00000000-0000-0000-0000-000000000003",
        login: "expired",
        display_name: "Бывший редактор",
        status: "active",
        roles: ["student"],
        editor_expires_at: "2020-01-01T10:00:00Z",
      },
      {
        id: "00000000-0000-0000-0000-000000000004",
        login: "disabled",
        display_name: "Заблокированный пользователь",
        status: "disabled",
        roles: ["student"],
        editor_expires_at: null,
      },
    ],
    total: 4,
  };
}

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("temporary editor management", () => {
  it("shows active, expired and blocked access without administrator controls", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockImplementation(() => jsonResponse(managedUsers())),
    );
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Пользователи и временные редакторы" }),
    ).toBeVisible();
    expect(screen.getByText("Учётных записей: 4")).toBeVisible();
    expect(screen.getByText("Администратор изменяется отдельным защищённым действием.")).toBeVisible();
    expect(screen.getByText(/Доступ истёк:/)).toBeVisible();
    expect(screen.getByText("Заблокирован")).toBeVisible();
    expect(
      within(articleFor("Главный администратор")).getByRole("button", {
        name: "Сбросить пароль",
      }),
    ).toBeVisible();
    expect(
      within(articleFor("Главный администратор")).queryByRole("button", {
        name: "Заблокировать",
      }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /назначить администратором/i })).not.toBeInTheDocument();
  });

  it("creates, grants, revokes and blocks through bounded Russian actions", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    let editorActive = false;
    const fetchMock = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.endsWith("/admin/users") && (init?.method === undefined || init.method === "GET")) {
        return jsonResponse(managedUsers(editorActive));
      }
      if (url.endsWith("/admin/users/editors") && init?.method === "POST") {
        return jsonResponse({
          id: "00000000-0000-0000-0000-000000000005",
          login: "new-editor",
          display_name: "Новый редактор",
          roles: ["student", "editor"],
          permissions: ["components.view", "components.edit"],
        });
      }
      if (url.endsWith("/00000000-0000-0000-0000-000000000002/editor")) {
        if (init?.method === "PUT") editorActive = true;
        if (init?.method === "DELETE") editorActive = false;
        return jsonResponse({
          status: init?.method === "PUT" ? "editor_granted" : "editor_revoked",
        });
      }
      if (url.endsWith("/00000000-0000-0000-0000-000000000002/disable")) {
        return jsonResponse({ status: "disabled" });
      }
      if (
        url.endsWith("/00000000-0000-0000-0000-000000000003/password") &&
        init?.method === "PUT"
      ) {
        return jsonResponse({ status: "password_reset" });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const confirmMock = vi.fn(() => true);
    vi.stubGlobal("confirm", confirmMock);
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <UserManagementPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByRole("heading", { name: "Пользователи и временные редакторы" });
    await user.type(screen.getByLabelText("Логин"), "new-editor");
    await user.type(screen.getByLabelText("Отображаемое имя"), "Новый редактор");
    await user.type(screen.getByLabelText("Временный пароль"), "long-editor-password");
    await user.click(screen.getByRole("button", { name: "Создать редактора" }));
    expect(await screen.findByText("Учётная запись временного редактора создана.")).toBeVisible();

    const createCall = fetchMock.mock.calls.find(
      ([request, options]) =>
        requestUrl(request).endsWith("/admin/users/editors") && options?.method === "POST",
    );
    const createBody = callBody(createCall);
    const parsedCreateBody = JSON.parse(createBody) as Record<string, unknown>;
    expect(parsedCreateBody).toMatchObject({
      login: "new-editor",
      display_name: "Новый редактор",
      password: "long-editor-password",
    });
    expect(typeof parsedCreateBody.editor_expires_at).toBe("string");
    expect(createBody).not.toContain("administrator");
    expect(new Headers(createCall?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-value");

    const expiredArticle = articleFor("Бывший редактор");
    await user.click(within(expiredArticle).getByRole("button", { name: "Сбросить пароль" }));
    await user.type(within(expiredArticle).getByLabelText("Новый пароль"), "replacement-password");
    await user.type(
      within(expiredArticle).getByLabelText("Подтверждение пароля"),
      "replacement-password",
    );
    await user.click(
      within(expiredArticle).getByRole("button", { name: "Сохранить новый пароль" }),
    );
    expect(
      await screen.findByText("Пароль изменён. Все прежние сеансы пользователя завершены."),
    ).toBeVisible();
    const passwordCall = fetchMock.mock.calls.find(
      ([request, options]) =>
        requestUrl(request).endsWith("/00000000-0000-0000-0000-000000000003/password") &&
        options?.method === "PUT",
    );
    expect(JSON.parse(callBody(passwordCall))).toEqual({ password: "replacement-password" });
    expect(new Headers(passwordCall?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-value");

    await user.click(
      within(articleFor("Активный редактор")).getByRole("button", {
        name: "Назначить редактором",
      }),
    );
    expect(await screen.findByText("Временный доступ редактора назначен.")).toBeVisible();
    await waitFor(() => {
      expect(
        within(articleFor("Активный редактор")).getByRole("button", {
          name: "Отозвать досрочно",
        }),
      ).toBeVisible();
    });
    const grantCall = fetchMock.mock.calls.find(
      ([request, options]) =>
        requestUrl(request).endsWith("/00000000-0000-0000-0000-000000000002/editor") &&
        options?.method === "PUT",
    );
    const parsedGrantBody = JSON.parse(callBody(grantCall)) as Record<string, unknown>;
    expect(Object.keys(parsedGrantBody)).toEqual(["editor_expires_at"]);
    expect(typeof parsedGrantBody.editor_expires_at).toBe("string");

    await user.click(
      within(articleFor("Активный редактор")).getByRole("button", {
        name: "Отозвать досрочно",
      }),
    );
    expect(await screen.findByText("Доступ редактора отозван досрочно.")).toBeVisible();
    await user.click(
      within(articleFor("Активный редактор")).getByRole("button", {
        name: "Заблокировать",
      }),
    );
    expect(await screen.findByText("Учётная запись заблокирована.")).toBeVisible();
    expect(confirmMock.mock.calls).toContainEqual([
      "Заблокировать пользователя «Активный редактор»?",
    ]);
    expect(
      fetchMock.mock.calls.some(
        ([request, options]) =>
          requestUrl(request).endsWith("/00000000-0000-0000-0000-000000000002/editor") &&
          options?.method === "DELETE",
      ),
    ).toBe(true);
  });
});
