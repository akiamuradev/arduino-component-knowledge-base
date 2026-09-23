import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { ThemeContext, type ThemePreference } from "./context";
import { ACCENT_PRESETS, accentHex, accentTokens, normalizeHex, type AccentPreset } from "./colors";
import { MAX_SAVED_ACCENTS, PREFERENCES_KEY, isTheme, parsePreferences, persistPreferences, readPreferences } from "./preferences";

const DARK_QUERY = "(prefers-color-scheme: dark)";

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState(readPreferences);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(DARK_QUERY).matches);
  const preference = preferences.theme;
  const resolvedTheme = preference === "system" ? (systemDark ? "dark" : "light") : preference;
  const accentColor = accentHex(preferences.accent);
  const tokens = useMemo(() => accentTokens(accentColor, resolvedTheme), [accentColor, resolvedTheme]);

  useEffect(() => {
    const media = window.matchMedia(DARK_QUERY);
    const update = () => { setSystemDark(media.matches); };
    media.addEventListener("change", update);
    return () => { media.removeEventListener("change", update); };
  }, []);
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = resolvedTheme;
    root.dataset.themePreference = preference;
    root.style.colorScheme = resolvedTheme;
    Object.entries(tokens).forEach(([key, value]) => { root.style.setProperty(key, value); });
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolvedTheme === "dark" ? "#1C1E1B" : "#F4EEE4");
  }, [preference, resolvedTheme, tokens]);
  useEffect(() => { persistPreferences(preferences); }, [preferences]);
  useEffect(() => {
    const update = (event: StorageEvent) => {
      if (event.key !== PREFERENCES_KEY) return;
      const next = parsePreferences(event.newValue);
      if (next) setPreferences(next);
    };
    window.addEventListener("storage", update);
    return () => { window.removeEventListener("storage", update); };
  }, []);
  const setPreference = useCallback((theme: ThemePreference) => {
    if (isTheme(theme)) setPreferences((old) => ({ ...old, theme }));
  }, []);
  const setAccentPreset = useCallback((value: AccentPreset) => {
    if (Object.hasOwn(ACCENT_PRESETS, value)) setPreferences((old) => ({ ...old, accent: { type: "preset", value } }));
  }, []);
  const setCustomAccent = useCallback((value: string) => {
    const hex = normalizeHex(value);
    if (hex) setPreferences((old) => ({ ...old, accent: { type: "custom", value: hex } }));
  }, []);
  const saveCurrentAccent = useCallback(() => {
    setPreferences((old) => {
      if (old.accent.type !== "custom" || old.savedAccents.length >= MAX_SAVED_ACCENTS) return old;
      const hex = normalizeHex(old.accent.value);
      if (!hex || old.savedAccents.includes(hex)) return old;
      return { ...old, savedAccents: [...old.savedAccents, hex] };
    });
  }, []);
  const removeSavedAccent = useCallback((value: string) => {
    const hex = normalizeHex(value);
    if (hex) setPreferences((old) => ({ ...old, savedAccents: old.savedAccents.filter((saved) => saved !== hex) }));
  }, []);
  const value = useMemo(() => ({ preference, resolvedTheme, setPreference, accent: preferences.accent,
    accentColor, tokens, setAccentPreset, setCustomAccent, savedAccents: preferences.savedAccents,
    saveCurrentAccent, removeSavedAccent }),
  [preference, resolvedTheme, setPreference, preferences.accent, accentColor, tokens, setAccentPreset, setCustomAccent,
    preferences.savedAccents, saveCurrentAccent, removeSavedAccent]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
