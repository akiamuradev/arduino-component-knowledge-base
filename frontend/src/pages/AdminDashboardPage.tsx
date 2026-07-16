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
          <p className="eyebrow">Сегодня в редакции</p>
          <h2>Обзор материалов</h2>
        </div>
        <Link className="button button--primary" to="/admin/components/new">Новая карточка</Link>
      </div>
      <p className="lede">
        Управляйте карточками компонентов: готовьте черновики, проверяйте содержание и
        публикуйте материалы для студентов.
      </p>
      <div className="status-grid">
        <article className="status-card status-card--draft"><span className="status-card__icon" aria-hidden="true">✎</span><strong>{count("draft")}</strong><span>Черновики</span><small>Требуют подготовки</small></article>
        <article className="status-card status-card--published"><span className="status-card__icon" aria-hidden="true">✓</span><strong>{count("published")}</strong><span>Опубликовано</span><small>Доступны студентам</small></article>
        <article className="status-card status-card--archived"><span className="status-card__icon" aria-hidden="true">□</span><strong>{count("archived")}</strong><span>В архиве</span><small>Скрыты из каталога</small></article>
      </div>
      <div className="recent-list">
        <div className="section-heading section-heading--compact">
          <div><p className="eyebrow">Последние изменения</p><h3>Недавние карточки</h3></div>
          <Link className="text-link" to="/admin/components">Все карточки →</Link>
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
