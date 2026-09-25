import { expect, test } from "@playwright/test";
import { expectNoAccessibilityViolations, expectNoHorizontalOverflow } from "./support/accessibility";

const student = { id: "10000000-0000-4000-8000-000000000001", login: "student", display_name: "Студент", roles: ["student"], permissions: ["components.view", "components.create", "components.edit"] };

test("the editorial guide is not public", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({ status: 401, json: { detail: { code: "authentication_required" } } }));
  await page.goto("/editor-guide");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Правила заполнения карточек" })).toHaveCount(0);
});

test("authenticated guide renders canonical content responsively and editor shortcut preserves a draft", async ({ page, context }) => {
  await context.route("**/api/v1/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({ json: path.endsWith("/auth/me") ? student
      : path.endsWith("/workspace/categories") ? [{ id: "20000000-0000-4000-8000-000000000001", slug: "sensors", name: "Датчики" }] : [] });
  });
  await page.goto("/admin/components/new");
  const title = page.getByRole("textbox", { name: "Название", exact: true });
  await title.fill("HC-SR04 — черновик");
  const shortcut = page.getByRole("link", { name: /Правила заполнения/ });
  await expect(shortcut).toHaveAttribute("href", "/editor-guide");
  await expect(shortcut).toHaveAttribute("target", "_blank");
  await expect(shortcut).toHaveAttribute("rel", "noopener noreferrer");
  const popupPromise = page.waitForEvent("popup");
  await shortcut.click();
  const guide = await popupPromise;
  await expect(guide.getByRole("heading", { level: 1, name: "Правила заполнения карточек" })).toBeVisible();
  await expect(page).toHaveURL(/\/admin\/components\/new$/);
  await expect(title).toHaveValue("HC-SR04 — черновик");
  await expect(guide.getByRole("heading", { name: "Аннотация" })).toHaveAttribute("id", "guide-аннотация");
  await expect(guide.getByRole("cell", { name: "2–400 cm" })).toBeVisible();
  await expect(guide.getByText("выбирайте второй вариант.")).toBeVisible();
  for (const width of [1280, 320]) {
    await guide.setViewportSize({ width, height: 900 });
    for (const theme of ["Светлое", "Тёмное"]) {
      await guide.getByRole("button", { name: "Настройки сайта" }).click();
      await guide.getByRole("radio", { name: theme }).check();
      await guide.keyboard.press("Escape");
      await expectNoHorizontalOverflow(guide, `editor guide ${String(width)} ${theme}`);
      await expectNoAccessibilityViolations(guide, `editor guide ${String(width)} ${theme}`);
    }
  }
  await guide.goto("/editor-guide#guide-аннотация");
  await expect(guide.getByRole("heading", { name: "Аннотация" })).toBeInViewport();
  await guide.close();
  await expect(title).toHaveValue("HC-SR04 — черновик");
});
