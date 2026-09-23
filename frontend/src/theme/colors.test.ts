import { describe, expect, it } from "vitest";
import { ACCENT_PRESETS, accentTokens, contrast, hexToHsv, hexToRgb, hsvToHex, normalizeHex, onAccent } from "./colors";
import { PREFERENCES_KEY, parsePreferences, readPreferences } from "./preferences";

describe("accent color utilities", () => {
  it("normalizes RGB and round-trips HSV, including black and gray", () => {
    expect(normalizeHex(" b45cff ")).toBe("#B45CFF");
    expect(hexToRgb("#B45CFF")).toEqual({ r: 180, g: 92, b: 255 });
    for (const color of ["#000000", "#FFFFFF", "#808080", "#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#00FFFF", "#FF00FF", "#B45CFF"]) {
      expect(hsvToHex(hexToHsv(color))).toBe(color);
    }
  });
  it("derives readable text and control borders for both themes, even black/white accents", () => {
    const colors = [...Object.values(ACCENT_PRESETS).map((preset) => preset.hex), "#000000", "#FFFFFF", "#777777", "#B45CFF"];
    for (const color of colors) {
      expect(contrast(onAccent(color), color)).toBeGreaterThanOrEqual(4.5);
      for (const theme of ["light", "dark"] as const) {
        const tokens = accentTokens(color, theme);
        for (const surface of theme === "light" ? ["#F4EEE4", "#FBF7EF", "#FFFDF8", "#ECE3D5"] : ["#1C1E1B", "#232620", "#292C27", "#343832"]) {
          expect(contrast(tokens["--color-accent-text"], surface)).toBeGreaterThanOrEqual(4.5);
          expect(contrast(tokens["--color-accent-border"], surface)).toBeGreaterThanOrEqual(3);
        }
        expect(Object.keys(tokens).every((key) => key.startsWith("--color-accent") || key === "--color-on-accent")).toBe(true);
      }
    }
  });
  it("rejects malformed/future preferences without accepting unknown or prototype presets", () => {
    for (const value of [null, "broken", "{}", '{"version":2}', JSON.stringify({ version: 1, theme: "dark", accent: { type: "preset", value: "toString" } }),
      JSON.stringify({ version: 1, theme: "dark", accent: { type: "custom", value: "#bad" } })]) {
      expect(parsePreferences(value)).toBeNull();
    }
    localStorage.setItem("ackb-theme", "dark");
    localStorage.setItem(PREFERENCES_KEY, "broken");
    expect(readPreferences().theme).toBe("dark");
    localStorage.setItem(PREFERENCES_KEY, JSON.stringify({ version: 1, theme: "light", accent: { type: "custom", value: "b45cff" }, password: "discard" }));
    expect(readPreferences()).toEqual({ version: 1, theme: "light", accent: { type: "custom", value: "#B45CFF" } });
  });
});
