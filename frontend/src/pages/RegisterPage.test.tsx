import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/query-client";
import { ThemeProvider } from "../theme/ThemeProvider";
import { RegisterPage } from "./RegisterPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("registration page", () => {
  it("submits only credentials, establishes the student session and opens catalog", async () => {
    const fetchMock = vi.fn<typeof fetch>((input, options) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.endsWith("/auth/register") && options?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({
          user: {
            id: "00000000-0000-0000-0000-000000000010",
            login: "new-student",
            display_name: "new-student",
            roles: ["student"],
            permissions: ["components.view"],
          },
          expires_at: "2099-01-01T00:00:00Z",
        }), { headers: { "Content-Type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({
        error: { code: "authentication_required" },
      }), { status: 401, headers: { "Content-Type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
    const user = userEvent.setup();

    render(
      <ThemeProvider>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={["/register"]}>
            <Routes>
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/" element={<h1>Каталог</h1>} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </ThemeProvider>,
    );

    await screen.findByRole("heading", { name: "Создать аккаунт" });
    await user.type(screen.getByLabelText("Логин"), "new-student");
    await user.type(screen.getByLabelText("Пароль"), "safe-student-password");
    await user.type(screen.getByLabelText("Подтверждение пароля"), "safe-student-password");
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(await screen.findByRole("heading", { name: "Каталог" })).toBeVisible();

    const registration = fetchMock.mock.calls.find(([, options]) => options?.method === "POST");
    const body = registration?.[1]?.body;
    if (typeof body !== "string") throw new Error("registration body must be JSON");
    expect(JSON.parse(body)).toEqual({ login: "new-student", password: "safe-student-password" });
    expect(body).not.toContain("role");
    expect(body).not.toContain("permission");
    expect(body).not.toContain("display_name");
  });

  it("shows a clear duplicate-login error", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>((_input, options) => Promise.resolve(
      options?.method === "POST"
        ? new Response(JSON.stringify({ error: { code: "login_already_exists" } }), {
            status: 409,
            headers: { "Content-Type": "application/json" },
          })
        : new Response(JSON.stringify({ error: { code: "authentication_required" } }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          }),
    )));
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
    const user = userEvent.setup();
    render(
      <ThemeProvider><QueryClientProvider client={client}><MemoryRouter>
        <RegisterPage />
      </MemoryRouter></QueryClientProvider></ThemeProvider>,
    );
    await screen.findByRole("heading", { name: "Создать аккаунт" });
    await user.type(screen.getByLabelText("Логин"), "existing-user");
    await user.type(screen.getByLabelText("Пароль"), "safe-student-password");
    await user.type(screen.getByLabelText("Подтверждение пароля"), "safe-student-password");
    await user.click(screen.getByRole("button", { name: "Создать аккаунт" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Этот логин уже занят");
  });
});
