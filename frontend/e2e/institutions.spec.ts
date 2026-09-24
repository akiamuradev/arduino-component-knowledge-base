import { expect, test } from "@playwright/test";
import { expectNoAccessibilityViolations, expectNoHorizontalOverflow } from "./support/accessibility";

test("institution cards retain logo mapping, keyboard access and mobile theme layout", async ({ page }) => {
  await page.goto("/license");
  const section = page.getByRole("region", { name: /Связано с образовательными организациями/ });
  const college = section.locator('a[href="https://mpk.lgpu.org/"]');
  const university = section.locator('a[href="https://lgpu.org/"]');
  for (const [card, source] of [[college, "/branding/college-mpk-lgpu.png"], [university, "/branding/university-lgpu.png"]] as const) {
    await expect(card).toHaveAttribute("target", "_blank");
    await expect(card).toHaveAttribute("rel", "noopener noreferrer");
    await expect(card.locator("img")).toHaveAttribute("src", source);
    await card.scrollIntoViewIfNeeded();
    await expect.poll(() => card.locator("img").evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    await expect(card.locator("img")).toHaveCSS("object-fit", "contain");
  }
  await college.focus();
  await page.keyboard.press("Tab");
  await expect(university).toBeFocused();
  await expect(university).toHaveCSS("outline-style", "solid");
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["Светлое", "Тёмное"]) {
      await page.getByRole("button", { name: "Настройки сайта" }).click();
      await page.getByRole("radio", { name: theme }).check();
      await page.getByRole("radio", { name: "Violet" }).check();
      await page.keyboard.press("Escape");
      await section.scrollIntoViewIfNeeded();
      await expect(college).toBeVisible();
      await expect(university).toBeVisible();
      const first = await college.boundingBox();
      const second = await university.boundingBox();
      expect(first?.height).toBe(second?.height);
      expect(first?.height).toBeGreaterThanOrEqual(44);
      await expectNoHorizontalOverflow(page, `institutions ${String(width)} ${theme}`);
      await expectNoAccessibilityViolations(page, `institutions ${String(width)} ${theme}`);
    }
  }
});

test("About shows expanded institutions without mobile overflow", async ({ page }) => {
  await page.route("**/api/v1/auth/me", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ id: "10000000-0000-4000-8000-000000000001", login: "student", display_name: "Студент", roles: ["student"], permissions: ["components.view"] }),
  }));
  await page.goto("/about");
  const section = page.locator(".about-page").getByRole("region", { name: "Связано с образовательными организациями" });
  await expect(section.getByText("Многопрофильный педагогический колледж ЛГПУ", { exact: true })).toBeVisible();
  await expect(section.getByText("Луганский государственный педагогический университет", { exact: true })).toBeVisible();
  for (const width of [1280, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await section.scrollIntoViewIfNeeded();
    await expectNoHorizontalOverflow(page, `About institutions ${String(width)}`);
    await expectNoAccessibilityViolations(page, `About institutions ${String(width)}`);
    const cards = section.locator("a");
    const first = await cards.nth(0).boundingBox();
    const second = await cards.nth(1).boundingBox();
    expect(first?.height).toBeGreaterThanOrEqual(88);
    expect(second?.height).toBeGreaterThanOrEqual(88);
  }
});
