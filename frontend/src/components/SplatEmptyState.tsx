import type { ReactNode } from "react";

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

        <span>{icon}</span>
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
