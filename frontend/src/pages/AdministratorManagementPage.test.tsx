import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/query-client";
import { AdministratorManagementPage } from "./AdministratorManagementPage";

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("administrator management", () => {
  it("lists active administrators and creates one without client-owned roles", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    let total = 1;
    const fetchMock = vi.fn<typeof fetch>((input, options) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/admin/users/administrators") && options?.method === "POST") {
        total = 2;
        return Promise.resolve(new Response(JSON.stringify({
          id: "00000000-0000-0000-0000-000000000002",
          login: "second-admin",
          display_name: "second-admin",
          roles: ["administrator"],
          permissions: ["users.manage", "roles.assign"],
        }), { headers: { "Content-Type": "application/json" } }));
      }
      if (url.endsWith("/admin/users/administrators")) {
        const items = [
          {
            id: "00000000-0000-0000-0000-000000000001",
            login: "admin",
            display_name: "admin",
            status: "active",
            roles: ["administrator"],
            editor_expires_at: null,
          },
        ];
        if (total === 2) items.push({
          id: "00000000-0000-0000-0000-000000000002",
          login: "second-admin",
          display_name: "second-admin",
          status: "active",
          roles: ["administrator"],
          editor_expires_at: null,
        });
        return Promise.resolve(new Response(JSON.stringify({ items, total }), {
          headers: { "Content-Type": "application/json" },
        }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
    const user = userEvent.setup();

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter><AdministratorManagementPage /></MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByRole("heading", { name: "Администраторы" });
    expect(screen.getByText("Действующих: 1")).toBeVisible();
    await user.type(screen.getByLabelText("Логин"), "second-admin");
    await user.type(screen.getByLabelText("Новый пароль"), "safe-admin-password");
    await user.type(screen.getByLabelText("Подтверждение пароля"), "safe-admin-password");
    await user.click(screen.getByRole("button", { name: "Создать администратора" }));
    expect(await screen.findByText("Учётная запись администратора создана.")).toBeVisible();

    const createCall = fetchMock.mock.calls.find(([, options]) => options?.method === "POST");
    const body = createCall?.[1]?.body;
    if (typeof body !== "string") throw new Error("administrator body must be JSON");
    expect(JSON.parse(body)).toEqual({ login: "second-admin", password: "safe-admin-password" });
    expect(body).not.toContain("role");
    expect(body).not.toContain("permission");
    expect(body).not.toContain("display_name");
    expect(new Headers(createCall?.[1]?.headers).get("X-CSRF-Token")).toBe("csrf-value");
  });
});
