import { Link } from "react-router-dom";

import { hasPermission } from "../auth/permissions";
import { useCurrentUser } from "../auth/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { SplatEmptyState } from "../components/SplatEmptyState";
import { COMPONENT_STATUS_LABELS } from "../config/uiLabels";
import { useWorkspaceComponents } from "../workspace/queries";

export function ComponentListPage() {
  const components = useWorkspaceComponents();
  const currentUser = useCurrentUser();
  const canCreate = currentUser.data === undefined
    ? false
    : hasPermission(currentUser.data, "components.create");
  if (components.isPending) {
    return <LoadingState label="Загружаем карточки…" />;
  }
  if (components.isError) {
    return (
      <ErrorState
        message="Не удалось получить карточки с сервера."
        onRetry={() => void components.refetch()}
      />
    );
  }

  return (
    <section>
      <div className="section-heading">
        <div><p className="eyebrow">Материалы редакции</p><h2>Карточки компонентов</h2><p className="section-description">Подготовка, проверка, публикация и архив в одном списке.</p></div>
        {canCreate ? <Link className="button button--primary" to="/admin/components/new">Новая карточка</Link> : null}
      </div>
      {components.data.items.length === 0 ? (
        <SplatEmptyState icon="▤" title="Карточек пока нет" description="Создайте первый черновик вручную." action={canCreate ? <Link className="button button--primary" to="/admin/components/new">Новая карточка</Link> : undefined} />
      ) : (
        <div className="component-table" role="list">
          <div className="component-table__head" aria-hidden="true"><span>Название</span><span>Категория</span><span>Состояние</span><span>Версия</span></div>
          {components.data.items.map((component) => (
            <Link role="listitem" className="component-row" key={component.id} to={`/admin/components/${component.id}/edit`}>
              <span><strong>{component.title}</strong><small>{component.summary}</small>{component.sources.length === 0 ? null : <small className="origin-label">Импортировано · {component.sources.length === 1 ? component.sources[0]?.license_spdx : `${String(component.sources.length)} источника`}</small>}</span>
              <span>{component.primary_category.name}</span>
              <span className={`status-badge status-badge--${component.status}`}>
                {COMPONENT_STATUS_LABELS[component.status]}
              </span>
              <span className="revision-label">Версия {component.revision}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
