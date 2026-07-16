import { NavLink, Outlet } from "react-router-dom";

import { useCurrentUser } from "../auth/queries";

export function AdminLayout() {
  const currentUser = useCurrentUser();
  const isAdministrator = currentUser.data?.roles.includes("administrator") === true;
  return (
    <div className="admin-grid">
      <aside className="admin-nav">
        <p className="eyebrow">Рабочая область</p>
        <h1>Редакция</h1>
        <nav aria-label="Рабочее место преподавателя">
          <NavLink end to="/admin">Обзор</NavLink>
          <NavLink to="/admin/components">Карточки</NavLink>
          <NavLink to="/admin/components/new">Новая карточка</NavLink>
          {isAdministrator ? <NavLink to="/admin/duplicates">Проверка дубликатов</NavLink> : null}
          {isAdministrator ? <NavLink to="/admin/jobs">Фоновые задачи</NavLink> : null}
        </nav>
        <NavLink className="back-link" to="/">← Вернуться в каталог</NavLink>
      </aside>
      <section className="admin-content"><Outlet /></section>
    </div>
  );
}
