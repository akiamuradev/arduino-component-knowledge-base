import { NavLink, Outlet } from "react-router-dom";

import { navigationFor } from "../app/navigation";
import { useCurrentUser } from "../auth/queries";
import { AppFooter } from "../components/AppFooter";
import { AppHeader } from "../components/AppHeader";

export function AdminLayout() {
  const currentUser = useCurrentUser();
  const user = currentUser.data;
  if (user === undefined) return null;
  const materialsNavigation = navigationFor(user, "materials");
  const administrationNavigation = navigationFor(user, "administration");
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
          <section className="admin-nav__section">
            <h2>Материалы</h2>
            {materialsNavigation.map((item) => (
              <NavLink end={item.end} key={item.path} to={item.path}>
                <span aria-hidden="true">{item.icon}</span>{item.label}
              </NavLink>
            ))}
          </section>
          {administrationNavigation.length === 0 ? null : (
            <section className="admin-nav__section">
              <h2>Администрирование</h2>
              {administrationNavigation.map((item) => (
                <NavLink end={item.end} key={item.path} to={item.path}>
                  <span aria-hidden="true">{item.icon}</span>{item.label}
                </NavLink>
              ))}
            </section>
          )}
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
