import type { CSSProperties } from "react";

import greenSplat from "../assets/brand/green-splat.svg";

type BrandSplatVariant = "default" | "muted" | "glow";

export interface BrandSplatProps {
  size?: number | string;
  className?: string;
  opacity?: number;
  rotation?: number;
  animated?: boolean;
  variant?: BrandSplatVariant;
  loading?: "eager" | "lazy";
}

type SplatStyle = CSSProperties & {
  "--splat-size": string;
  "--splat-opacity": number;
  "--splat-rotation": string;
};

export function BrandSplat({
  size = "12rem",
  className = "",
  opacity = 1,
  rotation = 0,
  animated = false,
  variant = "default",
  loading = "lazy",
}: BrandSplatProps) {
  const resolvedSize = typeof size === "number" ? `${String(size)}px` : size;
  const classes = [
    "brand-splat",
    `brand-splat--${variant}`,
    animated ? "brand-splat--animated" : "",
    className,
  ].filter(Boolean).join(" ");
  const style: SplatStyle = {
    "--splat-size": resolvedSize,
    "--splat-opacity": Math.max(0, Math.min(1, opacity)),
    "--splat-rotation": `${String(rotation)}deg`,
  };

  return (
    <img
      alt=""
      aria-hidden="true"
      className={classes}
      draggable={false}
      loading={loading}
      src={greenSplat}
      style={style}
    />
  );
}
