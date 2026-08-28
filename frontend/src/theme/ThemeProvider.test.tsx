import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ThemeToggle } from "../components/ThemeToggle";
import { ThemeProvider } from "./ThemeProvider";

describe("theme provider", () => {
  it("persists explicit light and dark choices", async () => {
    const user = userEvent.setup();
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    const trigger = screen.getByRole("button", { name: /Оформление:/ });
    expect(trigger).toHaveAttribute("title", "Настроить оформление");
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger.querySelector("svg")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/[☼☾◐]/);
    await user.click(trigger);
    expect(screen.getByRole("menu", { name: "Выбор оформления" })).toBeVisible();
    expect(screen.getByRole("menuitemradio", { name: "Как на устройстве" }))
      .toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: "Тёмное" }));
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("dark"); });
    expect(window.localStorage.getItem("ackb-theme")).toBe("dark");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(screen.getByRole("menuitemradio", { name: "Тёмное" }))
      .toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: "Светлое" }));
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("light"); });
  });

  it("resolves and follows the system color scheme", async () => {
    window.localStorage.setItem("ackb-theme", "system");
    let dark = true;
    let changeListener: (() => void) | undefined;
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      get matches() { return query.includes("dark") && dark; },
      media: query,
      onchange: null,
      addEventListener: vi.fn((_event, listener: EventListenerOrEventListenerObject) => {
        if (typeof listener === "function") changeListener = () => { listener(new Event("change")); };
      }),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("dark"); });
    expect(document.documentElement.dataset.themePreference).toBe("system");
    dark = false;
    act(() => {
      changeListener?.();
    });
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("light"); });
  });

  it("supports keyboard navigation and returns focus after selection or escape", async () => {
    const user = userEvent.setup();
    render(<ThemeProvider><ThemeToggle /></ThemeProvider>);
    const trigger = screen.getByRole("button", { name: /Оформление:/ });
    trigger.focus();

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitemradio", { name: "Светлое" })).toHaveFocus();
    await user.keyboard("{ArrowDown}{Enter}");
    await waitFor(() => { expect(document.documentElement.dataset.theme).toBe("dark"); });
    expect(trigger).toHaveFocus();

    await user.keyboard("{ArrowUp}");
    expect(screen.getByRole("menuitemradio", { name: "Как на устройстве" })).toHaveFocus();
    await user.keyboard("{Home}");
    expect(screen.getByRole("menuitemradio", { name: "Светлое" })).toHaveFocus();
    await user.keyboard("{End}");
    expect(screen.getByRole("menuitemradio", { name: "Как на устройстве" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.keyboard("{Enter}");
    expect(screen.getByRole("menuitemradio", { name: "Тёмное" })).toHaveFocus();
    await user.tab();
    await waitFor(() => {
      expect(screen.queryByRole("menu", { name: "Выбор оформления" })).not.toBeInTheDocument();
    });
  });
});
