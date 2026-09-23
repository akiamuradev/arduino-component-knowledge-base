import { createContext, useContext } from "react";
import type { Accent, AccentPreset } from "./colors";

export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = Exclude<ThemePreference, "system">;

export interface ThemeContextValue {
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
  setPreference: (preference: ThemePreference) => void;
  accent: Accent;
  accentColor: string;
  tokens: Record<string, string>;
  setAccentPreset: (preset: AccentPreset) => void;
  setCustomAccent: (hex: string) => void;
}

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used inside ThemeProvider");
  }
  return context;
}
