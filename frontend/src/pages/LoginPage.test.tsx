import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/query-client";
import { ThemeProvider } from "../theme/ThemeProvider";
import { LoginPage } from "./LoginPage";

describe("login page", () => {
  it("reflects auth flow without allowing the OLED access choice to define permissions", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockImplementation((_input, options) => {
      if (options?.method === "POST") {
        return Promise.resolve(new Response(JSON.stringify({ detail: { code: "invalid_credentials" } }), { status: 401, headers: { "Content-Type": "application/json" } }));
      }
      return Promise.resolve(new Response(JSON.stringify({ detail: { code: "authentication_required" } }), { status: 401, headers: { "Content-Type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = createQueryClient();
    const user = userEvent.setup();
    const view = render(<ThemeProvider><QueryClientProvider client={client}><MemoryRouter><LoginPage /></MemoryRouter></QueryClientProvider></ThemeProvider>);
    await screen.findByRole("heading", { name: "Вход в систему" });
    await user.click(screen.getByRole("radio", { name: /Редакция/ }));
    expect(view.container).toHaveTextContent("ADMIN");
    await user.type(screen.getByLabelText("Логин"), "admin");
    await user.type(screen.getByLabelText("Пароль"), "invalid-password");
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось войти");
    expect(view.container).toHaveTextContent("ACCESS DENIED");
    await user.type(screen.getByLabelText("Логин"), "2");
    await waitFor(() => { expect(screen.queryByRole("alert")).not.toBeInTheDocument(); });
    expect(view.container).toHaveTextContent("ADMIN");
    const body = fetchMock.mock.calls.find(([, options]) => options?.method === "POST")?.[1]?.body;
    if (typeof body !== "string") throw new Error("login request body must be a string");
    const submitted = JSON.parse(body) as Record<string, unknown>;
    expect(submitted).toEqual({ login: "admin", password: "invalid-password" });
    expect(submitted).not.toHaveProperty("role");
    expect(screen.getByRole("link", { name: /GitHub автора/ })).toHaveAttribute("rel", "noopener noreferrer");
  });
});
