import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SiteSettingsButton } from "../components/SiteSettingsButton";
import { ThemeProvider } from "./ThemeProvider";
import { ACCENT_PRESETS } from "./colors";
import { PREFERENCES_KEY, parsePreferences } from "./preferences";

const current = () => parsePreferences(localStorage.getItem(PREFERENCES_KEY));
const mount = () => render(<ThemeProvider><SiteSettingsButton /></ThemeProvider>);
async function open() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Настройки сайта" }));
  return user;
}

describe("site appearance preferences", () => {
  it.each(["light", "dark", "system"] as const)("silently migrates legacy %s and defaults to green", (theme) => {
    localStorage.setItem("ackb-theme", theme);
    mount();
    expect(document.documentElement.dataset.themePreference).toBe(theme);
    expect(document.documentElement.dataset.theme).toBe(theme === "dark" ? "dark" : "light");
    expect(current()).toEqual({ version: 2, theme, accent: { type: "preset", value: "green" }, savedAccents: [] });
    expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#32CD32");
  });

  it("selects every preset and persists across remounts", async () => {
    const view = mount();
    const user = await open();
    for (const [key, preset] of Object.entries(ACCENT_PRESETS)) {
      const radio = screen.getByRole("radio", { name: preset.label });
      await user.click(radio);
      expect(radio).toBeChecked();
      expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe(preset.hex);
      expect(current()?.accent).toEqual({ type: "preset", value: key });
    }
    view.unmount();
    mount();
    await open();
    expect(screen.getByRole("radio", { name: "Orange" })).toBeChecked();
  });

  it("synchronizes custom HEX, RGB and brightness, rejects invalid drafts, and preserves the accent across themes", async () => {
    const view = mount();
    const user = await open();
    await user.click(screen.getByRole("radio", { name: "Свой цвет" }));
    const hex = screen.getByRole("textbox", { name: "HEX" });
    fireEvent.change(hex, { target: { value: "#B45CFF" } });
    expect(screen.getByLabelText("Красный (R)")).toHaveValue("180");
    expect(screen.getByLabelText("Зелёный (G)")).toHaveValue("92");
    expect(screen.getByLabelText("Синий (B)")).toHaveValue("255");
    expect(screen.getByRole("slider", { name: "Яркость" })).toHaveValue("100");
    fireEvent.change(screen.getByLabelText("Красный (R)"), { target: { value: "181" } });
    expect(hex).toHaveValue("#B55CFF");
    const saved = localStorage.getItem(PREFERENCES_KEY);
    for (const invalid of ["#123", "gggggg", "#FFFFFFFF", ""]) {
      fireEvent.change(hex, { target: { value: invalid } });
      expect(hex).toHaveAttribute("aria-invalid", "true");
      expect(localStorage.getItem(PREFERENCES_KEY)).toBe(saved);
      expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#B55CFF");
    }
    for (const invalid of ["256", "-1", "1.5", "", "abc"]) {
      fireEvent.change(screen.getByLabelText("Красный (R)"), { target: { value: invalid } });
      expect(screen.getByLabelText("Красный (R)")).toHaveAttribute("aria-invalid", "true");
      expect(localStorage.getItem(PREFERENCES_KEY)).toBe(saved);
    }
    fireEvent.change(hex, { target: { value: "#b45cff" } });
    expect(current()?.accent).toEqual({ type: "custom", value: "#B45CFF" });
    for (const theme of ["Тёмное", "Светлое"]) {
      await user.click(screen.getByRole("radio", { name: theme }));
      expect(current()?.accent).toEqual({ type: "custom", value: "#B45CFF" });
    }
    fireEvent.change(screen.getByRole("slider", { name: "Яркость" }), { target: { value: "0" } });
    expect(hex).toHaveValue("#000000");
    fireEvent.change(screen.getByRole("slider", { name: "Яркость" }), { target: { value: "100" } });
    expect(hex).toHaveValue("#B45CFF");
    view.unmount();
    mount();
    await open();
    expect(screen.getByLabelText("HEX")).toHaveValue("#B45CFF");
  });

  it("supports keyboard opening and radio navigation, Escape and focus return", async () => {
    mount();
    const user = userEvent.setup();
    const trigger = screen.getByRole("button", { name: "Настройки сайта" });
    trigger.focus();
    await user.keyboard("{Enter}");
    const dialog = screen.getByRole("dialog", { name: "Настройки сайта" });
    expect(screen.getByRole("button", { name: "Закрыть настройки сайта" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("link", { name: "Ссылка" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Закрыть настройки сайта" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("radio", { name: "Как на устройстве" })).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(screen.getByRole("radio", { name: "Тёмное" })).toBeChecked();
    // Browser Escape emits cancel on a native dialog (covered end-to-end too).
    fireEvent(dialog, new Event("cancel", { bubbles: false, cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("follows system changes without losing the accent", async () => {
    let dark = true;
    let changed: (() => void) | undefined;
    vi.spyOn(window, "matchMedia").mockImplementation((query: string) => ({
      get matches() { return dark; }, media: query, onchange: null,
      addEventListener: vi.fn((_event, listener: EventListenerOrEventListenerObject) => {
        if (typeof listener === "function") changed = () => { listener(new Event("change")); };
      }), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }));
    mount();
    const user = await open();
    await user.click(screen.getByRole("radio", { name: "Blue" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    dark = false;
    act(() => { changed?.(); });
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(current()?.accent).toEqual({ type: "preset", value: "blue" });
  });

  it("keeps working when browser storage is unavailable", async () => {
    vi.spyOn(localStorage, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    mount();
    const user = await open();
    await user.click(screen.getByRole("radio", { name: "Violet" }));
    expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#A970FF");
  });

  it("reads valid cross-tab changes but ignores malformed ones", () => {
    mount();
    const record = { version: 2, theme: "dark", accent: { type: "custom", value: "#B45CFF" }, savedAccents: [] };
    act(() => { window.dispatchEvent(new StorageEvent("storage", { key: PREFERENCES_KEY, newValue: JSON.stringify(record) })); });
    expect(current()).toEqual(record);
    act(() => { window.dispatchEvent(new StorageEvent("storage", { key: PREFERENCES_KEY, newValue: "broken" })); });
    expect(current()).toEqual(record);
  });
});
