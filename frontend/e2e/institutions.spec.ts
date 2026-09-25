import { expect, test } from "@playwright/test";
import { expectNoAccessibilityViolations, expectNoHorizontalOverflow } from "./support/accessibility";

test("footer is compact without resizing institution chips or losing content", async ({ page }) => {
  await page.goto("/license");
  const footer = page.locator("footer");
  // The three-column layout keeps a strict height budget, but not a machine-specific text height.
  for (const [width, maxHeight, chipHeight] of [
    [1440, 145, 74], [768, 205, 74], [390, 395, 90], [320, 415, 90],
  ]) {
    await page.setViewportSize({ width, height: 900 });
    for (const theme of ["Светлое", "Тёмное"]) {
      await page.getByRole("button", { name: "Настройки сайта" }).click();
      await page.getByRole("radio", { name: theme }).check();
      await page.keyboard.press("Escape");
      await footer.scrollIntoViewIfNeeded();
      const bounds = await footer.boundingBox();
      expect(bounds?.height).toBeLessThanOrEqual(maxHeight);
      await expect(footer.locator(".app-footer__brand")).toContainText("Автор:");
      await expect(footer.getByRole("heading", { name: /Связано с образовательными организациями/ })).toBeVisible();
      for (const name of ["О системе", "Источники материалов", "GNU GPL v3.0 или новее"]) {
        await expect(footer.getByRole("link", { name, exact: true })).toBeVisible();
      }
      await expect(footer.locator(".build-info")).toBeVisible();
      for (const card of await footer.locator(".institution-card").all()) {
        const chip = await card.boundingBox();
        expect(chip?.width).toBeGreaterThanOrEqual(180);
        expect(chip?.height).toBe(chipHeight);
        await expect(card).toHaveCSS("padding", "8px");
        await expect(card).toHaveCSS("gap", "8px");
      }
      const brand = await footer.locator(".app-footer__brand").boundingBox();
      const institutions = await footer.locator(".institutions").boundingBox();
      const services = await footer.locator(".app-footer__services").boundingBox();
      if (!brand || !institutions || !services) throw new Error("Footer columns missing");
      if (width >= 768) {
        expect(brand.x + brand.width).toBeLessThanOrEqual(institutions.x);
        expect(institutions.x + institutions.width).toBeLessThanOrEqual(services.x);
        const chips = await footer.locator(".institution-card").all();
        const first = await chips[0]?.boundingBox();
        const second = await chips[1]?.boundingBox();
        expect(first?.y).toBe(second?.y);
      } else {
        expect(brand.y + brand.height).toBeLessThanOrEqual(institutions.y);
        expect(institutions.y + institutions.height).toBeLessThanOrEqual(services.y);
        expect(Math.abs(institutions.x + institutions.width / 2 - width / 2)).toBeLessThan(1);
      }
      const links = await footer.locator("nav a").all();
      for (let index = 1; index < links.length; index += 1) {
        const before = await links[index - 1]?.boundingBox();
        const after = await links[index]?.boundingBox();
        expect(after?.y).toBeGreaterThanOrEqual((before?.y ?? 0) + (before?.height ?? 0));
      }
      await expectNoHorizontalOverflow(page, `compact footer ${String(width)} ${theme}`);
      await expectNoAccessibilityViolations(page, `compact footer ${String(width)} ${theme}`);
    }
  }
});

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
