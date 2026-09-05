import { Outlet, useLocation } from "react-router-dom";

import { AppFooter } from "../components/AppFooter";
import { AppHeader } from "../components/AppHeader";

export function StudentLayout() {
  const isCatalog = useLocation().pathname === "/";
  return (
    <div className="app-shell">
      <AppHeader />
      <main className={`page${isCatalog ? " page--catalog" : ""}`}><Outlet /></main>
      <AppFooter />
    </div>
  );
}
