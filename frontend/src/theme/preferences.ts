import { ACCENT_PRESETS, normalizeHex, type Accent, type AccentPreset } from "./colors";
import type { ThemePreference } from "./context";

export const PREFERENCES_KEY = "ackb-ui-preferences";
export interface UiPreferences { version: 1; theme: ThemePreference; accent: Accent }
export const DEFAULT_PREFERENCES: UiPreferences = { version: 1, theme: "system", accent: { type: "preset", value: "green" } };
export function isTheme(value: unknown): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
export function parsePreferences(raw: string | null): UiPreferences | null {
  try {
    const value: unknown = JSON.parse(raw ?? "null");
    if (!isRecord(value) || value.version !== 1 || !isTheme(value.theme) || !isRecord(value.accent)) return null;
    const accent = value.accent;
    if (accent.type === "preset" && typeof accent.value === "string" && Object.hasOwn(ACCENT_PRESETS, accent.value)) {
      return { version: 1, theme: value.theme, accent: { type: "preset", value: accent.value as AccentPreset } };
    }
    if (accent.type === "custom" && typeof accent.value === "string") {
      const hex = normalizeHex(accent.value);
      if (hex) return { version: 1, theme: value.theme, accent: { type: "custom", value: hex } };
    }
  } catch { /* Malformed or future settings fall back to the legacy preference. */ }
  return null;
}
export function readPreferences(): UiPreferences {
  try {
    const current = parsePreferences(window.localStorage.getItem(PREFERENCES_KEY));
    if (current) return current;
    const legacy = window.localStorage.getItem("ackb-theme");
    return { ...DEFAULT_PREFERENCES, theme: isTheme(legacy) ? legacy : "system" };
  } catch { return DEFAULT_PREFERENCES; }
}
export function persistPreferences(preferences: UiPreferences): void {
  try { window.localStorage.setItem(PREFERENCES_KEY, JSON.stringify(preferences)); }
  catch { /* Preferences still work for this page when storage is unavailable. */ }
}
