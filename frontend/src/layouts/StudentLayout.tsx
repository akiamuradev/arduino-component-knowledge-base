import { Outlet } from "react-router-dom";

import { AppFooter } from "../components/AppFooter";
import { AppHeader } from "../components/AppHeader";

export function StudentLayout() {
  return (
    <div className="app-shell">
      <AppHeader />
      <main className="page"><Outlet /></main>
      <AppFooter />
    </div>
  );
}
