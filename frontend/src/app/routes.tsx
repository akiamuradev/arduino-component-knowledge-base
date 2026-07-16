import type { RouteObject } from "react-router-dom";

import { AdminLayout } from "../layouts/AdminLayout";
import { StudentLayout } from "../layouts/StudentLayout";
import { AdminDashboardPage } from "../pages/AdminDashboardPage";
import { AdminJobsPage } from "../pages/AdminJobsPage";
import { CatalogPage } from "../pages/CatalogPage";
import { CatalogComponentPage } from "../pages/CatalogComponentPage";
import { ComponentEditorPage } from "../pages/ComponentEditorPage";
import { ComponentListPage } from "../pages/ComponentListPage";
import { LoginPage } from "../pages/LoginPage";
import { ForbiddenPage, NotFoundPage, RouteErrorPage } from "../pages/StatusPages";
import { RequireAnyRole, RequireAuthenticated } from "../routing/guards";

export const routes: RouteObject[] = [
  {
    path: "/login",
    element: <LoginPage />,
    errorElement: <RouteErrorPage />,
  },
  {
    element: <RequireAuthenticated />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <StudentLayout />,
        children: [
          { index: true, element: <CatalogPage /> },
          { path: "/components/:slug", element: <CatalogComponentPage /> },
        ],
      },
      {
        element: <RequireAnyRole roles={["teacher", "administrator"]} />,
        children: [
          {
            path: "/admin",
            element: <AdminLayout />,
            children: [
              { index: true, element: <AdminDashboardPage /> },
              { path: "components", element: <ComponentListPage /> },
              { path: "components/new", element: <ComponentEditorPage mode="new" /> },
              { path: "components/:componentId/edit", element: <ComponentEditorPage mode="edit" /> },
              {
                element: <RequireAnyRole roles={["administrator"]} />,
                children: [{ path: "jobs", element: <AdminJobsPage /> }],
              },
            ],
          },
        ],
      },
      { path: "/forbidden", element: <ForbiddenPage /> },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
];
