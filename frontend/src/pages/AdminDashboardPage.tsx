import { Link } from "react-router-dom";

import type { ComponentStatus } from "../api/contracts";
import { hasPermission } from "../auth/permissions";
import { useCurrentUser } from "../auth/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { BrandSplat } from "../components/BrandSplat";
import { SplatEmptyState } from "../components/SplatEmptyState";
import { COMPONENT_STATUS_LABELS } from "../config/uiLabels";
import { useWorkspaceComponents } from "../workspace/queries";

export function AdminDashboardPage() {
  const components = useWorkspaceComponents();
  const currentUser = useCurrentUser();
  const canCreate = currentUser.data === undefined
    ? false
    : hasPermission(currentUser.data, "components.create");

  if (components.isPending) {
    return <LoadingState label="Загружаем редакционный обзор…" />;
  }
  if (components.isError) {
    return (
      <ErrorState
        title="Обзор недоступен"
        message="Сервер не вернул список карточек."
        onRetry={() => void components.refetch()}
      />
    );
  }

  const count = (...statuses: ComponentStatus[]) =>
    components.data.items.filter((component) => statuses.includes(component.status)).length;

  return (
    <section>
      <div className="section-heading admin-dashboard-heading">
        <div>
          <p className="eyebrow">Сегодня в редакции</p>
          <h2>Обзор материалов</h2>
        </div>
        {canCreate ? <Link className="button button--primary" to="/admin/components/new">Новая карточка</Link> : null}
        <BrandSplat className="admin-dashboard-splat" opacity={0.62} rotation={-8} size="7rem" variant="muted" />
      </div>
      <p className="lede">
        Управляйте карточками компонентов: готовьте черновики, проверяйте содержание и
        публикуйте материалы для студентов.
      </p>
      <div className="status-grid">
        <article className="status-card status-card--draft"><span className="status-card__icon" aria-hidden="true">✎</span><strong>{count("draft", "changes_requested")}</strong><span>В работе</span><small>Черновики и исправления</small></article>
        <article className="status-card status-card--draft"><span className="status-card__icon" aria-hidden="true">⌕</span><strong>{count("in_review", "approved")}</strong><span>На проверке</span><small>Ожидают решения</small></article>
        <article className="status-card status-card--published"><span className="status-card__icon" aria-hidden="true">✓</span><strong>{count("published")}</strong><span>Опубликовано</span><small>Доступны студентам</small></article>
        <article className="status-card status-card--archived"><span className="status-card__icon" aria-hidden="true">□</span><strong>{count("hidden", "archived")}</strong><span>Не в каталоге</span><small>Скрытые и архивные</small></article>
      </div>
      <div className="recent-list">
        <div className="section-heading section-heading--compact">
          <div><p className="eyebrow">Последние изменения</p><h3>Недавние карточки</h3></div>
          <Link className="text-link" to="/admin/components">Все карточки →</Link>
        </div>
        {components.data.items.length === 0 ? (
          <SplatEmptyState icon="▤" title="Карточек пока нет" description="Создайте первый черновик и подготовьте его к публикации." />
        ) : components.data.items.slice(0, 5).map((component) => (
          <Link className="component-row" key={component.id} to={`/admin/components/${component.id}/edit`}>
            <span><strong>{component.title}</strong><small>{component.primary_category.name}</small></span>
            <span className={`status-badge status-badge--${component.status}`}>{COMPONENT_STATUS_LABELS[component.status]}</span>
            <span>Версия {component.revision}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
