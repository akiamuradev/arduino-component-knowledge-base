import { NavLink, Outlet } from "react-router-dom";

import { hasPermission } from "../auth/permissions";
import { useCurrentUser } from "../auth/queries";
import { AppFooter } from "../components/AppFooter";
import { AppHeader } from "../components/AppHeader";

export function AdminLayout() {
  const currentUser = useCurrentUser();
  const user = currentUser.data;
  if (user === undefined) return null;
  const canCreate = hasPermission(user, "components.create");
  const canImport = hasPermission(user, "imports.create");
  const canReview = hasPermission(user, "components.review");
  const canDiagnose = hasPermission(user, "system.diagnostics");
  const canViewUsers = hasPermission(user, "users.view");
  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page admin-grid">
        <aside className="admin-nav">
        <div className="admin-nav__heading">
          <p className="eyebrow">Рабочая область</p>
          <h1>Редакция</h1>
          <p>Управление учебными материалами и публикациями.</p>
        </div>
        <nav aria-label="Рабочее место редактора">
          <NavLink end to="/admin"><span aria-hidden="true">⌂</span>Обзор</NavLink>
          <NavLink to="/admin/components"><span aria-hidden="true">▤</span>Карточки</NavLink>
          {canCreate ? <NavLink to="/admin/components/new"><span aria-hidden="true">＋</span>Новая карточка</NavLink> : null}
          {canReview ? <NavLink to="/admin/duplicates"><span aria-hidden="true">◇</span>Дубликаты</NavLink> : null}
          {canImport ? <NavLink to="/admin/import"><span aria-hidden="true">⇣</span>Импорт</NavLink> : null}
          {canReview ? <NavLink to="/admin/import-reviews"><span aria-hidden="true">⌕</span>Проверка импорта</NavLink> : null}
          {canViewUsers ? <NavLink to="/admin/users"><span aria-hidden="true">♙</span>Пользователи</NavLink> : null}
          {canDiagnose ? <NavLink to="/admin/jobs"><span aria-hidden="true">↻</span>Фоновые задачи</NavLink> : null}
        </nav>
        <div className="admin-nav__footer">
          <span className="system-dot" aria-hidden="true" />
          <span><strong>Серверная авторизация</strong><small>Права проверяются сервером</small></span>
        </div>
        <NavLink className="back-link" to="/">← Вернуться в каталог</NavLink>
        </aside>
        <section className="admin-content"><Outlet /></section>
      </main>
      <AppFooter />
    </div>
  );
}
