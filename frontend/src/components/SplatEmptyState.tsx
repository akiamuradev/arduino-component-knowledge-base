import type { ReactNode } from "react";

import { BrandSplat } from "./BrandSplat";

export function SplatEmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="empty-panel">
      <div className="empty-panel__brand" aria-hidden="true">
        <BrandSplat size="clamp(7rem, 13vw, 10rem)" opacity={0.68} rotation={-5} variant="muted" />
        <span>{icon}</span>
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
