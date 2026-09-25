import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { expectControlTargets, expectNoAccessibilityViolations, expectNoHorizontalOverflow } from "./support/accessibility";

test("public license keeps the complete legal text and a responsive, keyboard-accessible TOC", async ({ page }) => {
  const apiRequests: string[] = [];
  await page.route("**/api/**", async (route) => { apiRequests.push(route.request().url()); await route.fulfill({ status: 401, body: "{}" }); });
  await page.goto("/license");
  await expect(page.getByRole("heading", { level: 1, name: "GNU General Public License" })).toBeVisible();
  const original = readFileSync(new URL("../../LICENCE", import.meta.url), "utf8");
  const normalize = (text: string) => text.replace(/\s+/g, " ").trim();
  expect(normalize(await page.locator(".license-document__body").innerText())).toBe(normalize(original));
  expect(apiRequests).toEqual([]);
  await expect(page.locator(".license-toc")).toHaveCSS("position", "sticky");
  await expect(page.getByRole("navigation", { name: "Оглавление лицензии" }).getByRole("link")).toHaveCount(20);
  await page.getByRole("link", { name: "15. Disclaimer of Warranty.", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#gpl-section-15$/);
  await expect(page.locator("#gpl-section-15")).toBeFocused();
  await page.reload();
  await expect(page.locator("#gpl-section-15")).toBeFocused();
  await page.setViewportSize({ width: 320, height: 900 });
  await expect(page.locator(".license-toc")).toHaveCSS("position", "static");
  await expect(page.locator(".license-toc details")).not.toHaveAttribute("open", "");
  await page.locator(".license-toc summary").click();
  await page.getByRole("link", { name: "0. Definitions.", exact: true }).click();
  await expect(page).toHaveURL(/#gpl-section-0$/);
  await expect(page.locator("#gpl-section-0")).toBeFocused();
  await expect(page.locator(".license-toc details")).not.toHaveAttribute("open", "");
  for (const theme of ["Светлое", "Тёмное"]) {
    await page.getByRole("button", { name: "Настройки сайта" }).click();
    await page.getByRole("radio", { name: theme }).check();
    await page.getByRole("radio", { name: "Violet" }).check();
    await page.keyboard.press("Escape");
    await expect(page.locator("html")).toHaveCSS("--color-accent", "#A970FF");
    await expectNoAccessibilityViolations(page, `license ${theme}`);
    await expectNoHorizontalOverflow(page, `license ${theme}`);
    await expectControlTargets(page, `license ${theme}`);
  }
  await expect(page.getByRole("link", { name: "GNU GPL v3.0 или новее" })).toHaveAttribute("href", "/license");
});
