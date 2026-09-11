import { expect, test } from "@playwright/test";

import { expectNoAccessibilityViolations, expectNoHorizontalOverflow } from "./support/accessibility";

test("legacy review is accessible on mobile and cannot apply without typed consent", async ({ page, context }) => {
  await context.addCookies([{ name: "ackb_csrf", value: "fixture", url: "http://127.0.0.1:4173" }]);
  await page.setViewportSize({ width: 320, height: 1000 });
  const administrator = { id: "admin", login: "admin", display_name: "Администратор",
    roles: ["administrator"], permissions: ["components.view", "components.edit", "imports.view", "imports.create", "imports.bulk_apply"] };
  let applied = false;
  const planHash = "a".repeat(64);
  const item = { id: "item", decision: "create", status: "planned", candidates: [],
    result_id: null, warnings: [], error_code: null,
    target: { title: "Модуль датчика DHT11", category: "ДАТЧИКИ", rows: [116], match: "unmatched",
      folder: null, description: "", specifications: [], images: [], candidates: [], warnings: [] } };
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown;
    if (path === "/api/v1/auth/me") body = administrator;
    else if (path === "/api/v1/legacy-imports") body = [{ id: "bundle", status: "ready", created_at: "2026-09-12T00:00:00Z" }];
    else if (path === "/api/v1/legacy-imports/bundle") body = {
      id: "bundle", status: applied ? "completed" : "ready", phase: "analysis", plan_hash: planHash,
      statistics: { targets: 1 }, items: [{ ...item, status: applied ? "applied" : "planned" }], error_code: null,
    };
    else if (path === "/api/v1/legacy-imports/bundle/apply") {
      expect(route.request().postDataJSON()).toEqual({ confirmation: "ИМПОРТ", plan_hash: planHash });
      applied = true;
      body = { status: "applying" };
    } else if (path === "/api/v1/import-jobs") body = { items: [], total: 0, limit: 50, offset: 0 };
    else body = [];
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(body) });
  });
  await page.goto("/admin/import?legacy=bundle");
  const apply = page.getByRole("button", { name: "Применить проверенный план" });
  await expect(apply).toBeDisabled();
  await page.getByText("Модуль датчика DHT11 · Создать черновик · Запланировано").click();
  await expectNoHorizontalOverflow(page, "legacy import mobile");
  await expectNoAccessibilityViolations(page, "legacy import mobile");
  expect(applied).toBe(false);
  await page.getByLabel("Для применения введите ИМПОРТ").fill("ИМПОРТ");
  await apply.click();
  await expect(page.getByRole("status")).toContainText("Обработка завершена");
  expect(applied).toBe(true);
});
