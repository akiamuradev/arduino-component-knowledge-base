export interface Rgb { r: number; g: number; b: number }
export interface Hsv { h: number; s: number; v: number }

export const ACCENT_PRESETS = {
  green: { label: "ACKB Green", hex: "#32CD32" },
  cyan: { label: "Cyan", hex: "#23C6D8" },
  blue: { label: "Blue", hex: "#4C8DFF" },
  violet: { label: "Violet", hex: "#A970FF" },
  orange: { label: "Orange", hex: "#FF9D3D" },
} as const;
export type AccentPreset = keyof typeof ACCENT_PRESETS;
export type Accent = { type: "preset"; value: AccentPreset } | { type: "custom"; value: string };

export function normalizeHex(value: string): string | null {
  const hex = value.trim().replace(/^#/, "");
  return /^[\da-f]{6}$/i.test(hex) ? `#${hex.toUpperCase()}` : null;
}
export function hexToRgb(hex: string): Rgb {
  const normalized = normalizeHex(hex);
  if (!normalized) throw new Error("Invalid RGB color");
  const value = Number.parseInt(normalized.slice(1), 16);
  return { r: (value >> 16) & 255, g: (value >> 8) & 255, b: value & 255 };
}
export const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));
export function rgbToHex({ r, g, b }: Rgb): string {
  return `#${[r, g, b].map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
}
export function hsvToHex({ h, s, v }: Hsv): string {
  const hue = ((h % 360) + 360) % 360 / 60;
  const c = clamp(v) * clamp(s);
  const x = c * (1 - Math.abs(hue % 2 - 1));
  const m = clamp(v) - c;
  const [r, g, b] = hue < 1 ? [c, x, 0] : hue < 2 ? [x, c, 0] : hue < 3 ? [0, c, x]
    : hue < 4 ? [0, x, c] : hue < 5 ? [x, 0, c] : [c, 0, x];
  return rgbToHex({ r: (r + m) * 255, g: (g + m) * 255, b: (b + m) * 255 });
}
export function hexToHsv(hex: string): Hsv {
  const rgb = hexToRgb(hex);
  const [r, g, b] = [rgb.r / 255, rgb.g / 255, rgb.b / 255];
  const max = Math.max(r, g, b), min = Math.min(r, g, b), delta = max - min;
  const h = delta === 0 ? 0 : max === r ? ((g - b) / delta) % 6
    : max === g ? (b - r) / delta + 2 : (r - g) / delta + 4;
  return { h: (h * 60 + 360) % 360, s: max === 0 ? 0 : delta / max, v: max };
}
function luminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex);
  const linear = (n: number) => {
    const v = n / 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return linear(r) * 0.2126 + linear(g) * 0.7152 + linear(b) * 0.0722;
}
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
export function onAccent(hex: string): string {
  return contrast(hex, "#000000") >= contrast(hex, "#FFFFFF") ? "#000000" : "#FFFFFF";
}
function mix(a: string, b: string, amount: number): string {
  const x = hexToRgb(a), y = hexToRgb(b);
  return rgbToHex({ r: x.r + (y.r - x.r) * amount, g: x.g + (y.g - x.g) * amount, b: x.b + (y.b - x.b) * amount });
}
export function accentHex(accent: Accent): string {
  return accent.type === "preset" ? ACCENT_PRESETS[accent.value].hex : accent.value;
}
export function accentTokens(hex: string, theme: "light" | "dark") {
  const dark = theme === "dark", alpha = dark ? 0.18 : 0.14;
  const surfaces = dark ? ["#1C1E1B", "#232620", "#292C27", "#343832"]
    : ["#F4EEE4", "#FBF7EF", "#FFFDF8", "#ECE3D5"];
  const backgrounds = [...surfaces, ...surfaces.map((surface) => mix(surface, hex, alpha))];
  const readable = (minimum: number) => {
    for (let step = 0; step <= 100; step++) {
      const candidate = mix(hex, dark ? "#FFFFFF" : "#000000", step / 100);
      if (backgrounds.every((bg) => contrast(candidate, bg) >= minimum)) return candidate;
    }
    return dark ? "#FFFFFF" : "#000000";
  };
  const { r, g, b } = hexToRgb(hex);
  return {
    "--color-accent": hex,
    "--color-accent-soft": `rgba(${String(r)}, ${String(g)}, ${String(b)}, ${String(alpha)})`,
    "--color-accent-border": readable(3),
    "--color-accent-text": readable(4.5),
    "--color-on-accent": onAccent(hex),
  };
}
