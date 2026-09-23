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
  await page.getByRole("button", { name: "Настройки сайта" }).click();
  await page.getByRole("radio", { name: label }).click();
  await page.keyboard.press("Escape");
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

test("site settings support keyboard, custom color, contrast and focus return at 320px", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await mockLoggedOut(page);
  await page.addInitScript(() => { localStorage.setItem("ackb-theme", "dark"); });
  await page.goto("/login");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const trigger = page.getByRole("button", { name: "Настройки сайта" });
  await trigger.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Настройки сайта" });
  await expect(dialog).toBeVisible();
  await expect(page.getByRole("button", { name: "Закрыть настройки сайта" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("radio", { name: "Тёмное" })).toBeFocused();
  await page.getByRole("radio", { name: "Свой цвет" }).check();
  await page.getByLabel("HEX", { exact: true }).fill("#B45CFF");
  await expect(page.getByLabel("Красный (R)")).toHaveValue("180");
  await expect(page.getByLabel("Зелёный (G)")).toHaveValue("92");
  await expect(page.getByLabel("Синий (B)")).toHaveValue("255");
  await page.getByLabel("Красный (R)").fill("256");
  await expect(page.getByLabel("Красный (R)")).toHaveAttribute("aria-invalid", "true");
  await expect(page.locator("html")).toHaveCSS("--color-accent", "#B45CFF");
  await page.getByLabel("Красный (R)").fill("180");
  for (const theme of ["Светлое", "Тёмное"]) {
    await page.getByRole("radio", { name: theme }).check();
    for (const hex of ["#B45CFF", "#FFFFFF", "#000000"]) {
      await page.getByLabel("HEX", { exact: true }).fill(hex);
      await expectNoAccessibilityViolations(page, `settings ${theme} ${hex}`);
    }
    await expectNoHorizontalOverflow(page, `settings ${theme}`);
  }
  // Native dialog cycles focus internally even when the preview is the last control.
  await page.getByRole("link", { name: "Ссылка", exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Закрыть настройки сайта" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await page.reload();
  await trigger.click();
  await expect(page.getByLabel("HEX", { exact: true })).toHaveValue("#000000");
  await page.keyboard.press("Escape");
});

test("saved palette migrates, stays accessible at 320px and preserves the active color on deletion", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await mockLoggedOut(page);
  await page.addInitScript(() => {
    if (!localStorage.getItem("ackb-ui-preferences")) localStorage.setItem("ackb-ui-preferences", JSON.stringify({
      version: 1, theme: "dark", accent: { type: "custom", value: "#B45CFF" },
    }));
  });
  await page.goto("/login");
  await page.getByRole("button", { name: "Настройки сайта" }).click();
  await expect(page.getByLabel("HEX", { exact: true })).toHaveValue("#B45CFF");
  await page.getByRole("button", { name: "Сохранить цвет" }).click();
  const swatch = page.getByRole("button", { name: "#B45CFF", exact: true });
  await expect(swatch).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("HEX", { exact: true }).fill("broken");
  await expect(page.getByRole("button", { name: "Сохранить цвет" })).toBeDisabled();
  await swatch.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("HEX", { exact: true })).toHaveValue("#B45CFF");
  for (const theme of ["Светлое", "Тёмное"]) {
    await page.getByRole("radio", { name: theme }).check();
    await expectNoAccessibilityViolations(page, `saved accents ${theme}`);
    await expectNoHorizontalOverflow(page, `saved accents ${theme}`);
    await expectControlTargets(page, `saved accents ${theme}`);
  }
  await page.reload();
  await page.getByRole("button", { name: "Настройки сайта" }).click();
  await expect(swatch).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Удалить цвет #B45CFF" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Мои цвета" })).toHaveCount(0);
  await expect(page.getByRole("radio", { name: "Свой цвет" })).toBeFocused();
  await expect(page.getByLabel("HEX", { exact: true })).toHaveValue("#B45CFF");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Настройки сайта" })).toBeFocused();
});

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
  await page.getByLabel("Пароль", { exact: true }).fill("incorrect-password");
  const remember = page.getByRole("checkbox", { name: "Запомнить на этом устройстве" });
  await expect(remember).not.toBeChecked();
  await remember.focus();
  await page.keyboard.press("Space");
  await expect(remember).toBeChecked();
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Не удалось войти. Проверьте данные или повторите позже.",
  );
  await expect(remember).toBeChecked();
});

test("password controls fit mobile auth fields in both themes", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await mockLoggedOut(page);
  for (const path of ["/login", "/register"]) {
    await page.goto(path);
    for (const theme of ["Светлое", "Тёмное"] as const) {
      await selectTheme(page, theme);
      await auditPage(page, `${path} password controls ${theme}`, 7);
      const field = page.getByLabel("Пароль", { exact: true });
      await field.fill("visible-test-password");
      const toggle = page.getByRole("button", { name: "Показать пароль", exact: true }).first();
      await toggle.click();
      await expect(field).toHaveAttribute("type", "text");
      await expect(field).toHaveValue("visible-test-password");
      await expect(field).toBeFocused();
      expect(await field.evaluate((input) => parseFloat(getComputedStyle(input).paddingRight))).toBeGreaterThanOrEqual(44);
      await page.getByRole("button", { name: "Скрыть пароль", exact: true }).click();
      await expect(field).toHaveAttribute("type", "password");
    }
  }
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
  await page.getByLabel("Характеристика 1").fill("Напряжение питания");
  await page.getByLabel("Значение характеристики 1").fill("5 В");
  await page.getByLabel("Характеристика 2").fill("Архитектура");
  await page.getByLabel("Значение характеристики 2").fill("8-bit AVR");
  await expect(page.getByRole("button", { name: "Удалить характеристику 1" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Удалить характеристику 2" })).toBeVisible();
  await expectNoHorizontalOverflow(page, "specification editor dark mobile");
  await expectNoAccessibilityViolations(page, "specification editor dark mobile");
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
