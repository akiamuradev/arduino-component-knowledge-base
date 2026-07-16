import { Link } from "react-router-dom";

import type { ComponentStatus } from "../api/contracts";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { useWorkspaceComponents } from "../workspace/queries";

const statusLabels: Record<ComponentStatus, string> = {
  draft: "Черновик",
  published: "Опубликовано",
  archived: "Архив",
};

const originLabels = {
  manual: "Создано вручную",
  imported: "Импортировано",
  mixed: "Дополнено редактором",
};

export function ComponentListPage() {
  const components = useWorkspaceComponents();
  if (components.isPending) {
    return <LoadingState label="Загружаем карточки…" />;
  }
  if (components.isError) {
    return (
      <ErrorState
        message="Не удалось получить карточки из backend."
        onRetry={() => void components.refetch()}
      />
    );
  }

  return (
    <section>
      <div className="section-heading">
        <div><p className="eyebrow">Материалы редакции</p><h2>Карточки компонентов</h2><p className="section-description">Черновики, опубликованные материалы и архив в одном списке.</p></div>
        <Link className="button button--primary" to="/admin/components/new">Новая карточка</Link>
      </div>
      {components.data.items.length === 0 ? (
        <div className="empty-panel"><h3>Карточек пока нет</h3><p>Создайте первый ручной draft.</p></div>
      ) : (
        <div className="component-table" role="list">
          <div className="component-table__head" aria-hidden="true"><span>Название</span><span>Категория</span><span>Статус</span><span>Версия</span></div>
          {components.data.items.map((component) => (
            <Link role="listitem" className="component-row" key={component.id} to={`/admin/components/${component.id}/edit`}>
              <span><strong>{component.title}</strong><small>{component.summary}</small>{component.origin ? <small className="origin-label">{originLabels[component.origin]}</small> : null}</span>
              <span>{component.primary_category.name}</span>
              <span className={`status-badge status-badge--${component.status}`}>
                {statusLabels[component.status]}
              </span>
              <span className="revision-label">rev. {component.revision}</span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
