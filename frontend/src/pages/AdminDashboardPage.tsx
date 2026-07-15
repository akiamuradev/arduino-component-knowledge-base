import { Link } from "react-router-dom";

import { ErrorState, LoadingState } from "../components/AsyncStates";
import { useWorkspaceComponents } from "../workspace/queries";

export function AdminDashboardPage() {
  const components = useWorkspaceComponents();

  if (components.isPending) {
    return <LoadingState label="Загружаем редакционный dashboard…" />;
  }
  if (components.isError) {
    return (
      <ErrorState
        title="Dashboard недоступен"
        message="Backend workspace API не вернул карточки. Ошибка не заменена тестовыми данными."
        onRetry={() => void components.refetch()}
      />
    );
  }

  const count = (status: "draft" | "published" | "archived") =>
    components.data.items.filter((component) => component.status === status).length;

  return (
    <section>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Рабочее место преподавателя</p>
          <h2>Редакционный dashboard</h2>
        </div>
        <Link className="button button--primary" to="/admin/components/new">Новая карточка</Link>
      </div>
      <p className="lede">
        Статусы получены из backend. Публикация требует валидной revision, а merge дубликатов
        остаётся отдельным действием administrator.
      </p>
      <div className="status-grid">
        <article><strong>{count("draft")}</strong><span>Черновики</span></article>
        <article><strong>{count("published")}</strong><span>Опубликовано</span></article>
        <article><strong>{count("archived")}</strong><span>В архиве</span></article>
      </div>
      <div className="recent-list">
        <div className="section-heading section-heading--compact">
          <h3>Недавние карточки</h3>
          <Link to="/admin/components">Все карточки</Link>
        </div>
        {components.data.items.length === 0 ? (
          <p className="muted">Карточек пока нет.</p>
        ) : components.data.items.slice(0, 5).map((component) => (
          <Link className="component-row" key={component.id} to={`/admin/components/${component.id}/edit`}>
            <span><strong>{component.title}</strong><small>{component.primary_category.name}</small></span>
            <span className={`status-badge status-badge--${component.status}`}>{component.status}</span>
            <span>rev. {component.revision}</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
