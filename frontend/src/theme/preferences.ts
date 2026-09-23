import { ACCENT_PRESETS, normalizeHex, type Accent, type AccentPreset } from "./colors";
import type { ThemePreference } from "./context";

export const PREFERENCES_KEY = "ackb-ui-preferences";
export const MAX_SAVED_ACCENTS = 12;
export interface UiPreferences { version: 2; theme: ThemePreference; accent: Accent; savedAccents: string[] }
export const DEFAULT_PREFERENCES: UiPreferences = { version: 2, theme: "system", accent: { type: "preset", value: "green" }, savedAccents: [] };
export function normalizeSavedAccents(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const colors = new Set<string>();
  for (const item of value) {
    const hex = typeof item === "string" ? normalizeHex(item) : null;
    if (hex) colors.add(hex);
    if (colors.size === MAX_SAVED_ACCENTS) break;
  }
  return [...colors];
}
export function isTheme(value: unknown): value is ThemePreference {
  return value === "light" || value === "dark" || value === "system";
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
export function parsePreferences(raw: string | null): UiPreferences | null {
  try {
    const value: unknown = JSON.parse(raw ?? "null");
    if (!isRecord(value) || (value.version !== 1 && value.version !== 2) || !isTheme(value.theme) || !isRecord(value.accent)) return null;
    const savedAccents = value.version === 2 ? normalizeSavedAccents(value.savedAccents) : [];
    const accent = value.accent;
    if (accent.type === "preset" && typeof accent.value === "string" && Object.hasOwn(ACCENT_PRESETS, accent.value)) {
      return { version: 2, theme: value.theme, accent: { type: "preset", value: accent.value as AccentPreset }, savedAccents };
    }
    if (accent.type === "custom" && typeof accent.value === "string") {
      const hex = normalizeHex(accent.value);
      if (hex) return { version: 2, theme: value.theme, accent: { type: "custom", value: hex }, savedAccents };
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
