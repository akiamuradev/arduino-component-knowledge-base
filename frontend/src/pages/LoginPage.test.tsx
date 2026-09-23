import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/query-client";
import { ThemeProvider } from "../theme/ThemeProvider";
import { LoginPage } from "./LoginPage";

describe("login page", () => {
  it("opens shared site settings before authentication without submitting credentials", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<ThemeProvider><QueryClientProvider client={createQueryClient()}><MemoryRouter><LoginPage /></MemoryRouter></QueryClientProvider></ThemeProvider>);
    await user.click(screen.getByRole("button", { name: "Настройки сайта" }));
    expect(screen.getByRole("dialog", { name: "Настройки сайта" })).toBeVisible();
    await user.click(screen.getByRole("radio", { name: "Cyan" }));
    expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#23C6D8");
    await user.click(screen.getByRole("button", { name: "Закрыть настройки сайта" }));
    expect(screen.getByRole("button", { name: "Настройки сайта" })).toHaveFocus();
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(0);
  });
  it.each([false, true])("submits credentials and remember=%s without a client-side role selector", async (remember) => {
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
    const checkbox = screen.getByRole("checkbox", { name: "Запомнить на этом устройстве" });
    expect(checkbox).not.toBeChecked();
    expect(screen.getByLabelText("Запомнить на этом устройстве")).toBe(checkbox);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(view.container).toHaveTextContent("СИСТЕМА ГОТОВА");
    const password = screen.getByLabelText("Пароль");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveAttribute("autocomplete", "current-password");
    expect(password).toHaveAttribute("maxlength", "128");
    expect(password).toBeRequired();
    await user.type(screen.getByLabelText("Логин"), "admin");
    await user.type(screen.getByLabelText("Пароль"), "invalid-password");
    const toggle = screen.getByRole("button", { name: "Показать пароль" });
    expect(toggle).toHaveAttribute("type", "button");
    await user.click(toggle);
    expect(password).toHaveAttribute("type", "text");
    expect(password).toHaveValue("invalid-password");
    expect(password).toHaveFocus();
    expect(toggle).toHaveAccessibleName("Скрыть пароль");
    await user.click(toggle);
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("invalid-password");
    await user.tab();
    expect(toggle).toHaveFocus();
    await user.keyboard(" ");
    expect(password).toHaveAttribute("type", "text");
    await user.keyboard("{Enter}");
    expect(password).toHaveAttribute("type", "password");
    expect(password).toHaveValue("invalid-password");
    expect(fetchMock.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(0);
    if (remember) {
      await user.tab();
      expect(checkbox).toHaveFocus();
      await user.keyboard(" ");
      expect(checkbox).toBeChecked();
    }
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось войти");
    expect(view.container).toHaveTextContent("ДОСТУП ЗАПРЕЩЁН");
    await user.click(screen.getByRole("button", { name: "Показать пароль" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Не удалось войти");
    await user.type(screen.getByLabelText("Логин"), "2");
    await waitFor(() => { expect(screen.queryByRole("alert")).not.toBeInTheDocument(); });
    expect(view.container).toHaveTextContent("СИСТЕМА ГОТОВА");
    const body = fetchMock.mock.calls.find(([, options]) => options?.method === "POST")?.[1]?.body;
    if (typeof body !== "string") throw new Error("login request body must be a string");
    const submitted = JSON.parse(body) as Record<string, unknown>;
    expect(submitted).toEqual({ login: "admin", password: "invalid-password", remember });
    expect(checkbox).toHaveProperty("checked", remember);
    expect(submitted).not.toHaveProperty("role");
    expect(screen.getByRole("link", { name: "Создать аккаунт" })).toHaveAttribute("href", "/register");
    expect(screen.getByRole("link", { name: /GitHub автора/ })).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("keeps the checked state during a pending request and after a failure", async () => {
    let finish: ((response: Response) => void) | undefined;
    const pending = new Promise<Response>((resolve) => { finish = resolve; });
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockImplementation((_input, options) => options?.method === "POST"
      ? pending : Promise.resolve(new Response("{}", { status: 401 }))));
    const user = userEvent.setup();
    render(<ThemeProvider><QueryClientProvider client={createQueryClient()}><MemoryRouter><LoginPage /></MemoryRouter></QueryClientProvider></ThemeProvider>);
    await user.type(screen.getByLabelText("Логин"), "student");
    await user.type(screen.getByLabelText("Пароль"), "test-password");
    const checkbox = screen.getByLabelText("Запомнить на этом устройстве");
    await user.click(checkbox);
    await user.click(screen.getByRole("button", { name: "Войти" }));
    expect(screen.getByRole("button", { name: "Проверяем…" })).toBeDisabled();
    expect(checkbox).toBeChecked();
    await act(async () => { finish?.(new Response("{}", { status: 401 })); await pending; });
    expect(await screen.findByRole("alert")).toHaveTextContent("Не удалось войти");
    expect(checkbox).toBeChecked();
  });
});
