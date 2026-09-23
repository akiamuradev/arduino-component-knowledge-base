import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SiteSettingsButton } from "../components/SiteSettingsButton";
import { ThemeProvider } from "./ThemeProvider";
import { useTheme, type ThemeContextValue } from "./context";
import { MAX_SAVED_ACCENTS, PREFERENCES_KEY, normalizeSavedAccents, parsePreferences, type UiPreferences } from "./preferences";

// Inspect the actual persisted record, not the sanitizing reader, so invalid
// writes / duplicates / missing schema migration cannot be hidden by parsing.
const current = () => JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? "null") as UiPreferences | null;
const mount = () => render(<ThemeProvider><SiteSettingsButton /></ThemeProvider>);
const changeHex = (value: string) => fireEvent.change(screen.getByLabelText("HEX"), { target: { value } });
async function open() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Настройки сайта" }));
  return user;
}

describe("saved accent preferences", () => {
  it.each(["light", "dark", "system"])("migrates v1 %s without losing theme or custom accent", (theme) => {
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ version: 1, theme, accent: { type: "custom", value: "#b45cff" } }));
    mount();
    expect(current()).toEqual({ version: 2, theme, accent: { type: "custom", value: "#B45CFF" }, savedAccents: [] });
    expect(document.documentElement.dataset.themePreference).toBe(theme);
    expect(document.documentElement.style.getPropertyValue("--color-accent")).toBe("#B45CFF");
  });

  it("migrates built-in v1 accents and sanitizes v2 palettes in insertion order", () => {
    const base = { theme: "dark", accent: { type: "preset", value: "violet" } };
    expect(parsePreferences(JSON.stringify({ ...base, version: 1 }))).toEqual({ ...base, version: 2, savedAccents: [] });
    const palette = ["b45cff", "#B45CFF", "bad", null, 23, "#ff9d3d", ...Array.from({ length: 15 }, (_, i) => `#${i.toString(16).padStart(6, "0")}`)];
    const savedAccents = normalizeSavedAccents(palette);
    expect(savedAccents).toHaveLength(MAX_SAVED_ACCENTS);
    expect(savedAccents.slice(0, 3)).toEqual(["#B45CFF", "#FF9D3D", "#000000"]);
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ ...base, version: 2, savedAccents: palette }));
    mount();
    expect(JSON.parse(localStorage.getItem(PREFERENCES_KEY) ?? "null")).toEqual({ ...base, version: 2, savedAccents });
    expect(normalizeSavedAccents({ color: "#FFFFFF" })).toEqual([]);
  });

  it("saves, reapplies and removes colors without resetting the active accent, including after remount", async () => {
    const view = mount();
    const user = await open();
    expect(screen.queryByRole("region", { name: "Мои цвета" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Свой цвет" }));
    changeHex("b45cff");
    await user.click(screen.getByRole("button", { name: "Сохранить цвет" }));
    expect(current()?.savedAccents).toEqual(["#B45CFF"]);
    expect(screen.getByRole("button", { name: "Сохранить цвет" })).toBeDisabled();
    changeHex("#FF9D3D");
    await user.click(screen.getByRole("button", { name: "Сохранить цвет" }));
    expect(current()?.savedAccents).toEqual(["#B45CFF", "#FF9D3D"]);
    await user.click(screen.getByRole("radio", { name: "Blue" }));
    const saved = screen.getByRole("button", { name: "#B45CFF" });
    expect(saved).toHaveAttribute("aria-pressed", "false");
    saved.focus();
    await user.keyboard("{Enter}");
    expect(saved).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("HEX")).toHaveValue("#B45CFF");
    expect(screen.getByLabelText("Красный (R)")).toHaveValue("180");
    view.unmount();
    const remounted = mount();
    await open();
    expect(current()?.savedAccents).toEqual(["#B45CFF", "#FF9D3D"]);
    const remove = screen.getByRole("button", { name: "Удалить цвет #B45CFF" });
    expect(remove.parentElement?.closest("label,button")).toBeNull();
    remove.focus();
    await user.keyboard("{Enter}");
    expect(current()?.savedAccents).toEqual(["#FF9D3D"]);
    expect(current()?.accent).toEqual({ type: "custom", value: "#B45CFF" });
    expect(screen.getByRole("button", { name: "#FF9D3D" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Удалить цвет #FF9D3D" }));
    expect(screen.queryByRole("region", { name: "Мои цвета" })).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Свой цвет" })).toHaveFocus();
    expect(current()?.accent).toEqual({ type: "custom", value: "#B45CFF" });
    remounted.unmount();
    mount();
    expect(current()?.savedAccents).toEqual([]);
  });

  it("disables saving any invalid HEX/RGB draft and recovers when corrected", async () => {
    mount();
    const user = await open();
    await user.click(screen.getByRole("radio", { name: "Свой цвет" }));
    const save = screen.getByRole("button", { name: "Сохранить цвет" });
    changeHex("#123456");
    changeHex("#bad");
    expect(save).toBeDisabled();
    await user.click(save);
    expect(current()?.savedAccents).toEqual([]);
    expect(current()?.accent).toEqual({ type: "custom", value: "#123456" });
    changeHex("#123456");
    expect(save).toBeEnabled();
    for (const label of ["Красный (R)", "Зелёный (G)", "Синий (B)"]) {
      const field = screen.getByLabelText(label);
      const previous = (field as HTMLInputElement).value;
      fireEvent.change(field, { target: { value: "256" } });
      expect(save).toBeDisabled();
      fireEvent.change(field, { target: { value: previous } });
      expect(save).toBeEnabled();
    }
    await user.click(save);
    expect(current()?.savedAccents).toEqual(["#123456"]);
    changeHex("broken");
    await user.click(screen.getByRole("button", { name: "#123456" }));
    expect(screen.getByLabelText("HEX")).toHaveValue("#123456");
  });

  it("enforces 12 colors in the UI and allows saving again after deletion", async () => {
    mount();
    const user = await open();
    await user.click(screen.getByRole("radio", { name: "Свой цвет" }));
    for (let i = 0; i < 12; i++) {
      changeHex(`#${i.toString(16).padStart(6, "0")}`);
      await user.click(screen.getByRole("button", { name: "Сохранить цвет" }));
    }
    changeHex("#ABCDEF");
    expect(screen.getByRole("button", { name: "Сохранить цвет" })).toBeDisabled();
    expect(screen.getByText("Можно сохранить до 12 цветов.")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "Мои цвета" })).getAllByRole("button")).toHaveLength(24);
    await user.click(screen.getByRole("button", { name: "Удалить цвет #000000" }));
    expect(screen.getByRole("button", { name: "Сохранить цвет" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Сохранить цвет" }));
    expect(current()?.savedAccents).toHaveLength(12);
    expect(current()?.savedAccents.at(-1)).toBe("#ABCDEF");
  });

  it("enforces duplicates and capacity inside the provider, independently of disabled controls", () => {
    let context: ThemeContextValue | undefined;
    function Probe() { context = useTheme(); return null; }
    render(<ThemeProvider><Probe /></ThemeProvider>);
    act(() => { context?.saveCurrentAccent(); });
    expect(current()?.savedAccents).toEqual([]);
    act(() => { context?.setCustomAccent("b45cff"); });
    act(() => { context?.saveCurrentAccent(); context?.saveCurrentAccent(); });
    expect(current()?.savedAccents).toEqual(["#B45CFF"]);
    for (let i = 0; i < 15; i++) {
      act(() => { context?.setCustomAccent(`#${i.toString(16).padStart(6, "0")}`); });
      act(() => { context?.saveCurrentAccent(); });
    }
    expect(current()?.savedAccents).toHaveLength(12);
    act(() => { context?.setCustomAccent("broken"); context?.saveCurrentAccent(); });
    expect(current()?.savedAccents).not.toContain("broken");
  });
});
