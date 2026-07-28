import type { RouteObject } from "react-router-dom";

import { AdminLayout } from "../layouts/AdminLayout";
import { StudentLayout } from "../layouts/StudentLayout";
import { AdminDashboardPage } from "../pages/AdminDashboardPage";
import { AdminJobsPage } from "../pages/AdminJobsPage";
import { AdminImportPage } from "../pages/AdminImportPage";
import { AboutPage } from "../pages/AboutPage";
import { CatalogPage } from "../pages/CatalogPage";
import { CatalogComponentPage } from "../pages/CatalogComponentPage";
import { ComponentEditorPage } from "../pages/ComponentEditorPage";
import { ComponentListPage } from "../pages/ComponentListPage";
import { DuplicateReviewPage } from "../pages/DuplicateReviewPage";
import { LoginPage } from "../pages/LoginPage";
import { ImportReviewPage } from "../pages/ImportReviewPage";
import { UserManagementPage } from "../pages/UserManagementPage";
import { SourcesPage } from "../pages/SourcesPage";
import { ForbiddenPage, NotFoundPage, RouteErrorPage } from "../pages/StatusPages";
import {
  RequireAuthenticated,
  RequirePermission,
} from "../routing/guards";

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
          { path: "/about", element: <AboutPage /> },
          { path: "/sources", element: <SourcesPage /> },
        ],
      },
      {
        element: <RequirePermission permission="components.edit" />,
        children: [
          {
            path: "/admin",
            element: <AdminLayout />,
            children: [
              { index: true, element: <AdminDashboardPage /> },
              { path: "components", element: <ComponentListPage /> },
              {
                element: <RequirePermission permission="components.create" />,
                children: [
                  { path: "components/new", element: <ComponentEditorPage mode="new" /> },
                ],
              },
              { path: "components/:componentId/edit", element: <ComponentEditorPage mode="edit" /> },
              {
                element: <RequirePermission permission="system.diagnostics" />,
                children: [
                  { path: "jobs", element: <AdminJobsPage /> },
                ],
              },
              {
                element: <RequirePermission permission="users.view" />,
                children: [
                  { path: "users", element: <UserManagementPage /> },
                ],
              },
              {
                element: <RequirePermission permission="imports.create" />,
                children: [
                  { path: "import", element: <AdminImportPage /> },
                ],
              },
              {
                element: <RequirePermission permission="components.review" />,
                children: [
                  { path: "import-reviews", element: <ImportReviewPage /> },
                  { path: "import-reviews/:reviewDraftId", element: <ImportReviewPage /> },
                  { path: "duplicates", element: <DuplicateReviewPage /> },
                  { path: "duplicates/:candidateId", element: <DuplicateReviewPage /> },
                ],
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
