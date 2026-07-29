import { expect, type Page, test } from "@playwright/test";

import {
  expectControlTargets,
  expectKeyboardFocusVisible,
  expectNoAccessibilityViolations,
  expectNoHorizontalOverflow,
} from "./support/accessibility";

const administrator = {
  id: "10000000-0000-4000-8000-000000000001",
  login: "administrator",
  display_name: "Алексей Администратор",
  roles: ["student", "teacher", "editor", "administrator"],
  permissions: [
    "components.view",
    "components.create",
    "components.edit",
    "components.archive",
    "components.delete",
    "components.submit_for_review",
    "components.review",
    "components.publish",
    "imports.view",
    "imports.create",
    "imports.retry",
    "imports.cancel",
    "users.view",
    "users.manage",
    "roles.assign",
    "audit.view",
    "system.settings",
    "system.diagnostics",
  ],
};

const category = {
  id: "20000000-0000-4000-8000-000000000001",
  slug: "sensors",
  name: "Датчики",
};

async function mockLoggedOut(page: Page): Promise<void> {
  await page.route("**/api/v1/auth/**", async (route) => {
    const loginAttempt = new URL(route.request().url()).pathname === "/api/v1/auth/login";
    await route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: loginAttempt ? "invalid_credentials" : "authentication_required",
          message: loginAttempt ? "Неверный логин или пароль." : "Войдите, чтобы продолжить.",
          retryable: false,
          request_id: "accessibility-login",
        },
      }),
    });
  });
}

async function mockAdministration(page: Page): Promise<void> {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(administrator),
      });
      return;
    }
    if (path === "/api/v1/workspace/categories") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([category]),
      });
      return;
    }
    if (path === "/api/v1/import-jobs") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items: [], total: 0, limit: 50, offset: 0 }),
      });
      return;
    }
    if (path === "/api/v1/admin/users") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [
            {
              id: "10000000-0000-4000-8000-000000000003",
              login: "student",
              display_name: "Мария Студентова",
              status: "active",
              roles: ["student"],
              editor_expires_at: null,
            },
          ],
          total: 1,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "unexpected_e2e_request",
          message: `Unexpected ${path}`,
          retryable: false,
          request_id: "accessibility-admin",
        },
      }),
    });
  });
}

async function selectTheme(page: Page, label: "Светлое" | "Тёмное"): Promise<void> {
  await page.getByRole("button", { name: /^Оформление:/ }).click();
  await page.getByRole("menuitemradio", { name: label }).click();
}

async function auditPage(
  page: Page,
  context: string,
  keyboardSteps = 8,
): Promise<void> {
  await expectNoAccessibilityViolations(page, context);
  await expectNoHorizontalOverflow(page, context);
  await expectControlTargets(page, context);
  await expectKeyboardFocusVisible(page, context, keyboardSteps);
}

test("login remains accessible by keyboard in both themes at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await mockLoggedOut(page);
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Вход в систему" })).toBeVisible();

  await selectTheme(page, "Светлое");
  await auditPage(page, "login light mobile", 5);
  await selectTheme(page, "Тёмное");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await auditPage(page, "login dark mobile", 5);

  await page.getByLabel("Логин").fill("student");
  await page.getByLabel("Пароль").fill("incorrect-password");
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Не удалось войти. Проверьте данные или повторите позже.",
  );
});

test("editor, import and user management pass responsive accessibility checks", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 1000 });
  await mockAdministration(page);

  await page.goto("/admin/components/new");
  await expect(page.getByRole("heading", { name: "Без названия" })).toBeVisible();
  await selectTheme(page, "Тёмное");
  await auditPage(page, "component editor dark mobile", 12);
  await page.getByRole("button", { name: "Добавить характеристику" }).click();
  await page.getByRole("button", { name: "Добавить характеристику" }).click();
  await expect(page.getByRole("button", { name: "Удалить характеристику 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Удалить характеристику 2" })).toBeVisible();
  const editorTab = page.getByRole("tab", { name: "Редактор" });
  await editorTab.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Предпросмотр" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  await page.goto("/admin/import");
  await expect(page.getByRole("heading", { name: "Загрузка компонентов" })).toBeVisible();
  await page.getByRole("button", { name: "Добавить компонент" }).click();
  await selectTheme(page, "Светлое");
  await auditPage(page, "component import light mobile", 12);

  await page.goto("/admin/users");
  await expect(
    page.getByRole("heading", { name: "Пользователи и временные редакторы" }),
  ).toBeVisible();
  await selectTheme(page, "Тёмное");
  await auditPage(page, "user management dark mobile", 12);

  await page.setViewportSize({ width: 1440, height: 1000 });
  await expectNoHorizontalOverflow(page, "user management desktop");
  await expectNoAccessibilityViolations(page, "user management dark desktop");
});
