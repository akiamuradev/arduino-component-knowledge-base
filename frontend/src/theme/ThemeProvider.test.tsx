import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "../components/ThemeToggle";
import { ThemeProvider } from "./ThemeProvider";

describe("theme provider", () => {
  it("persists explicit light and dark choices", async () => {
    const user = userEvent.setup();
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    await user.click(screen.getByRole("button", { name: "Тёмная тема" }));
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("dark"); });
    expect(window.localStorage.getItem("ackb-theme")).toBe("dark");
    expect(screen.getByRole("button", { name: "Тёмная тема" })).toHaveAttribute("aria-pressed", "true");
    await user.click(screen.getByRole("button", { name: "Светлая тема" }));
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("light"); });
  });

  it("resolves system theme from prefers-color-scheme", async () => {
    window.localStorage.setItem("ackb-theme", "system");
    vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
      matches: query.includes("dark"), media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(),
      removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }));
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("dark"); });
    expect(document.documentElement.dataset.themePreference).toBe("system");
  });
});
