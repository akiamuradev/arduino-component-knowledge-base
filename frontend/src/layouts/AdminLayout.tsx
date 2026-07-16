import { NavLink, Outlet } from "react-router-dom";

import { useCurrentUser } from "../auth/queries";
import { AppFooter } from "../components/AppFooter";
import { AppHeader } from "../components/AppHeader";

export function AdminLayout() {
  const currentUser = useCurrentUser();
  const isAdministrator = currentUser.data?.roles.includes("administrator") === true;
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
        <nav aria-label="Рабочее место преподавателя">
          <NavLink end to="/admin"><span aria-hidden="true">⌂</span>Обзор</NavLink>
          <NavLink to="/admin/components"><span aria-hidden="true">▤</span>Карточки</NavLink>
          <NavLink to="/admin/components/new"><span aria-hidden="true">＋</span>Новая карточка</NavLink>
          {isAdministrator ? <NavLink to="/admin/duplicates"><span aria-hidden="true">◇</span>Дубликаты</NavLink> : null}
          {isAdministrator ? <NavLink to="/admin/jobs"><span aria-hidden="true">↻</span>Фоновые задачи</NavLink> : null}
        </nav>
        <div className="admin-nav__footer">
          <span className="system-dot" aria-hidden="true" />
          <span><strong>Backend authorizes</strong><small>Права проверяются сервером</small></span>
        </div>
        <NavLink className="back-link" to="/">← Вернуться в каталог</NavLink>
        </aside>
        <section className="admin-content"><Outlet /></section>
      </main>
      <AppFooter />
    </div>
  );
}
