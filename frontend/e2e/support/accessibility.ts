import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

function violationSummary(
  violations: Awaited<ReturnType<AxeBuilder["analyze"]>>["violations"],
): string {
  return violations.map((violation) => {
    const targets = violation.nodes
      .flatMap((node) => node.target.map(String))
      .slice(0, 5)
      .join(", ");
    return `${violation.id} (${violation.impact ?? "unknown"}): ${targets}`;
  }).join("\n");
}

export async function expectNoAccessibilityViolations(
  page: Page,
  context: string,
): Promise<void> {
  await page.waitForTimeout(200);
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations,
    `${context}\n${violationSummary(results.violations)}`,
  ).toEqual([]);
}

export async function expectNoHorizontalOverflow(
  page: Page,
  context: string,
): Promise<void> {
  await page.evaluate(() => {
    document.documentElement.style.scrollBehavior = "auto";
    window.scrollTo(0, window.scrollY);
  });
  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    outsideViewport: [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => {
        const bounds = element.getBoundingClientRect();
        return bounds.right > window.innerWidth + 1 || bounds.left < -1;
      })
      .slice(0, 8)
      .map((element) => `${element.tagName.toLowerCase()}.${element.className}`),
  }));
  expect(
    layout.scrollWidth,
    `${context}: horizontal overflow: ${layout.outsideViewport.join(", ")}`,
  ).toBe(layout.clientWidth);
}

export async function expectKeyboardFocusVisible(
  page: Page,
  context: string,
  steps = 8,
): Promise<void> {
  await page.evaluate(() => {
    document.body.tabIndex = -1;
    document.body.focus();
  });
  for (let index = 0; index < steps; index += 1) {
    await page.keyboard.press("Tab");
    await page.waitForTimeout(250);
    const focus = await page.evaluate(() => {
      const active = document.activeElement;
      if (!(active instanceof HTMLElement)) return null;
      const bounds = active.getBoundingClientRect();
      let element: HTMLElement | null = active;
      let indicator = false;
      for (let depth = 0; depth < 3 && element !== null; depth += 1) {
        const style = getComputedStyle(element);
        indicator ||= (
          style.outlineStyle !== "none"
          && style.outlineWidth !== "0px"
        ) || (
          style.boxShadow !== "none"
          && style.boxShadow !== ""
        );
        element = element.parentElement;
      }
      return {
        tag: active.tagName.toLowerCase(),
        text: active.getAttribute("aria-label") ?? active.textContent.trim().slice(0, 80),
        indicator,
        visible: bounds.width > 0
          && bounds.height > 0
          && bounds.bottom > 0
          && bounds.right > 0
          && bounds.top < window.innerHeight
          && bounds.left < window.innerWidth,
      };
    });
    expect(focus, `${context}: Tab ${String(index + 1)} did not focus an element`).not.toBeNull();
    if (focus === null) throw new Error(`${context}: focus target missing`);
    expect(focus.visible, `${context}: hidden focus on ${focus.tag} ${focus.text}`).toBe(true);
    expect(
      focus.indicator,
      `${context}: no visible focus indicator on ${focus.tag} ${focus.text}`,
    ).toBe(true);
  }
}

export async function expectControlTargets(
  page: Page,
  context: string,
): Promise<void> {
  const undersized = await page.evaluate(() => {
    const selector = [
      "button",
      "summary",
      "a.button",
      "input:not([type='hidden']):not([type='checkbox']):not([type='radio'])",
      "select",
      "textarea",
    ].join(",");
    return [...document.querySelectorAll<HTMLElement>(selector)]
      .filter((element) => {
        const style = getComputedStyle(element);
        if (style.display === "none" || style.visibility === "hidden") return false;
        const bounds = element.getBoundingClientRect();
        return bounds.width > 0 && bounds.height > 0
          && (bounds.width < 24 || bounds.height < 24);
      })
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        const name = element.getAttribute("aria-label") ?? element.textContent.trim().slice(0, 50);
        return `${element.tagName.toLowerCase()}[${name}] ${String(Math.round(bounds.width))}x${String(Math.round(bounds.height))}`;
      });
  });
  expect(undersized, `${context}: undersized controls`).toEqual([]);
}
