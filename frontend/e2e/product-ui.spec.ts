import { expect, type Page, test } from "@playwright/test";

import {
  expectControlTargets,
  expectKeyboardFocusVisible,
  expectNoAccessibilityViolations,
} from "./support/accessibility";

const student = {
  id: "10000000-0000-4000-8000-000000000002",
  login: "student",
  display_name: "Мария Студентова",
  roles: ["student"],
  permissions: ["components.view"],
};

const editor = {
  ...student,
  login: "editor",
  display_name: "Ирина Редакторова",
  roles: ["student", "editor"],
  permissions: [
    "components.view",
    "components.create",
    "components.edit",
    "components.archive",
    "components.submit_for_review",
    "imports.view",
    "imports.create",
    "imports.retry",
    "imports.cancel",
  ],
};

const category = { id: "20000000-0000-4000-8000-000000000001", slug: "sensors", name: "Датчики" };
const component = {
  id: "30000000-0000-4000-8000-000000000001",
  slug: "dht22",
  title: "Датчик температуры DHT22",
  summary: "Цифровой датчик температуры и относительной влажности.",
  primary_category: category,
  aliases: ["AM2302"],
  manufacturer: "Aosong",
  model: "DHT22",
  tags: ["температура", "влажность", "digital"],
  description: "DHT22 измеряет температуру и относительную влажность и передаёт данные по однопроводному цифровому интерфейсу.",
  purpose: "Измерение параметров микроклимата.",
  usage_notes: "Установите подтягивающий резистор между линией данных и питанием.",
  safety_notes: "Перед подключением отключите питание макетной платы.",
  difficulty: "beginner",
  published_at: "2026-07-16T10:00:00Z",
  specifications: [
    { key: "supply-voltage", label: "Напряжение питания", value_text: "3.3–5.5", value_number: null, unit: "В", position: 0 },
    { key: "interface", label: "Интерфейс", value_text: "Digital", value_number: null, unit: null, position: 1 },
  ],
  compatibility: [{ target_type: "board", name: "Arduino Uno", version_constraint: "R3", notes: "Подключение к цифровому пину", position: 0 }],
  code_examples: [{
    title: "Прочитайте температуру", language: "arduino", practical_task: "Получите значение температуры и выведите его в Serial Monitor.",
    hints: ["Подключите библиотеку DHT."], body: "#include <DHT.h>\nvoid setup() { Serial.begin(9600); }", libraries: ["DHT sensor library"],
    explanation: "Значение можно читать после инициализации датчика.", visibility: "student", position: 0,
  }],
  media: [
    {
      asset_id: "40000000-0000-4000-8000-000000000001",
      kind: "image",
      purpose: "detail",
      alt_text: "Разъёмы DHT22",
      caption: "Контакты датчика",
      display_order: 0,
      is_primary: false,
      width: 800,
      height: 600,
      variants: [{
        name: "320w", mime: "image/webp", width: 320, height: 240,
        sha256: "1".repeat(64), url: "/media-storage/dht22-detail.svg?signed=1",
      }],
    },
    {
      asset_id: "40000000-0000-4000-8000-000000000002",
      kind: "image",
      purpose: "product",
      alt_text: "Основной вид DHT22",
      caption: "Датчик DHT22",
      display_order: 1,
      is_primary: true,
      width: 1600,
      height: 1200,
      variants: [{
        name: "320w", mime: "image/webp", width: 320, height: 240,
        sha256: "2".repeat(64), url: "/media-storage/dht22-primary.svg?signed=1",
      }],
    },
  ],
  sources: [{
    display_name: "Seeed Studio Wiki", original_url: "https://wiki.seeedstudio.com/Grove-Temperature_And_Humidity_Sensor_Pro/",
    repository_url: "https://github.com/Seeed-Studio/wiki-documents", license_name: "GNU General Public License v3.0 only",
    license_spdx: "GPL-3.0-only", license_url: "https://www.gnu.org/licenses/gpl-3.0.html", source_revision: "1234567890abcdef1234567890abcdef12345678",
    source_tag: "docusaurus-version", source_file_path: "sites/en/docs/Sensor/Grove/Grove-Temperature_And_Humidity_Sensor_Pro.md", source_entry_name: null,
    modifications_notice: "Facts extracted and normalized.", imported_at: "2026-07-15T10:00:00Z", attribution: "Based on Seeed Studio Wiki.",
    parser_name: "seeed-wiki-git-v1", parser_version: "1.0.0",
  }],
};

async function mockCatalog(page: Page, currentUser = student, items = [component], total = items.length) {
  await page.route("**/media-storage/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/svg+xml",
      body: "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"320\" height=\"240\"><rect width=\"320\" height=\"240\" fill=\"#168e52\"/></svg>",
    });
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(currentUser) });
      return;
    }
    if (path === "/api/v1/catalog/categories") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([category]) });
      return;
    }
    if (path === "/api/v1/catalog/components") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items, total }) });
      return;
    }
    if (path === "/api/v1/catalog/components/dht22") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(component) });
      return;
    }
    if (path === "/api/v1/workspace/components") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [], total: 0 }) });
      return;
    }
    await route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "unexpected_e2e_request", path } }) });
  });
}

async function mockLoggedOut(page: Page) {
  await page.route("**/api/v1/auth/me", async (route) => {
    await route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ detail: { code: "authentication_required" } }) });
  });
}

async function selectTheme(page: Page, label: "Светлое" | "Тёмное" | "Как на устройстве") {
  await page.getByRole("button", { name: /^Оформление:/ }).click();
  await page.getByRole("menuitemradio", { name: label }).click();
}

test("gallery keeps portrait and scheme geometry stable and opens a keyboard lightbox", async ({ page }) => {
  await mockCatalog(page);
  const media = [
    { ...component.media[1], width: 1200, height: 1600 },
    { ...component.media[0], width: 1800, height: 600 },
  ].map((item) => ({
    ...item, caption: "Фото и схема подключения",
    variants: [{ ...item.variants[0], width: item.width, height: item.height }],
  }));
  await page.route("**/api/v1/catalog/components/dht22", (route) =>
    route.fulfill({ json: { ...component, media } }));
  await page.route("**/media-storage/**", (route) => {
    const portrait = route.request().url().includes("primary");
    const width = portrait ? 1200 : 1800;
    const height = portrait ? 1600 : 600;
    return route.fulfill({
      contentType: "image/svg+xml",
      body: `<svg xmlns="http://www.w3.org/2000/svg" width="${String(width)}" height="${String(height)}"><rect width="100%" height="100%" fill="#168e52"/></svg>`,
    });
  });
  for (const width of [1440, 1024, 360]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/components/dht22");
    const viewport = page.locator(".media-gallery__viewport");
    await expect(viewport).toBeVisible();
    await expect.poll(() => viewport.locator("img").evaluate((img: HTMLImageElement) => img.naturalWidth / img.naturalHeight)).toBeCloseTo(1200 / 1600, 2);
    const before = await viewport.boundingBox();
    const hero = await page.locator(".student-card__hero").boundingBox();
    if (before === null) throw new Error("Missing gallery viewport");
    expect(before.width / before.height).toBeCloseTo(4 / 3, 1);
    await page.getByRole("button", { name: /Показать изображение 2/ }).click();
    await expect.poll(() => viewport.locator("img").evaluate((img: HTMLImageElement) => img.naturalWidth / img.naturalHeight)).toBeCloseTo(1800 / 600, 1);
    const after = await viewport.boundingBox();
    expect(after?.height).toBe(before.height);
    expect(after?.width).toBe(before.width);
    expect((await page.locator(".student-card__hero").boundingBox())?.height).toBe(hero?.height);
    await expect(viewport.locator("img")).toHaveCSS("object-fit", "contain");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await page.emulateMedia({ reducedMotion: "reduce" });
  const opener = page.locator(".media-gallery__viewport");
  await opener.click();
  const dialog = page.getByRole("dialog", { name: "Просмотр изображения" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute("aria-modal", "true");
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  await expect(dialog.getByRole("button", { name: "Закрыть просмотр изображения" })).toBeFocused();
  await dialog.getByRole("img").click();
  await expect(dialog).toBeVisible();
  await page.keyboard.press("ArrowLeft");
  await expect(dialog.getByRole("img", { name: "Основной вид DHT22" })).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(dialog.getByRole("img", { name: "Разъёмы DHT22" })).toBeVisible();
  await expect(dialog.getByRole("img")).toHaveCSS("object-fit", "contain");
  expect(await dialog.getByRole("img").evaluate((image) => {
    const box = image.getBoundingClientRect();
    return box.width <= innerWidth * 0.9 + 1 && box.height <= innerHeight * 0.9 + 1
      && box.left >= 0 && box.right <= innerWidth && box.top >= 0 && box.bottom <= innerHeight;
  })).toBe(true);
  await expectNoAccessibilityViolations(page, "image lightbox");
  await page.keyboard.press("Shift+Tab");
  expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
  await expect(dialog.getByRole("button", { name: "Следующее изображение" })).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Закрыть просмотр изображения" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
  await opener.click();
  await page.mouse.click(2, 2);
  await expect(dialog).toHaveCount(0);
  await expect(opener).toBeFocused();
});

test("inactive source cards keep names, badges and facts inside responsive columns", async ({ page }) => {
  await mockCatalog(page);
  const sources = ["AlexGyver", "Arduino-Tex", "Official KiCad Libraries", "Portal-PK", "Seeed Studio Wiki"].map((name, index) => ({
    key: `source-${String(index)}`, display_name: name,
    source_type: index === 2 ? "official_library" : "git_repository",
    status: index === 0 ? "disabled" : "inactive",
    content_policy: index === 2 ? "structured_metadata" : "facts_and_limited_adaptation",
    default_revision_policy: "immutable_commit", adapter_version: "1.1.0",
    license_name: "Creative Commons Attribution-ShareAlike 4.0 International",
    license_spdx: "CC-BY-SA-4.0", license_url: "https://creativecommons.org/licenses/by-sa/4.0/",
    repository_url: "https://github.com/Seeed-Studio/wiki-documents",
    attribution_template: `${name}, {source_file_path}: {source_entry_name}, revision {source_revision}`,
    disable_reason: index === 0 ? "owner_denied_usage" : "operator_disabled",
  }));
  await page.route("**/api/v1/catalog/sources", (route) => route.fulfill({ json: sources }));
  await page.goto("/sources");
  await expect(page.getByText("Активных источников пока нет")).toBeVisible();
  await expect(page.locator(".source-card")).toHaveCount(5);
  await selectTheme(page, "Тёмное");
  for (const width of [1440, 1024, 768, 360, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    const overflow = await page.locator(".source-card").evaluateAll((cards) =>
      cards.flatMap((card) => {
        const bounds = card.getBoundingClientRect();
        return [...card.querySelectorAll<HTMLElement>("header, h3, p, .status-badge, dl, dt, dd, a")]
          .filter((element) => {
            const box = element.getBoundingClientRect();
            return element.scrollWidth > element.clientWidth + 1
              || box.left < bounds.left - 1 || box.right > bounds.right + 1;
          })
          .map((element) => element.tagName);
      }),
    );
    expect(overflow, `source overflow at ${String(width)}px`).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  await expectNoAccessibilityViolations(page, "inactive sources dark mobile");
});

test("catalog uses a wide desktop workspace without changing other page widths", async ({ page }) => {
  const items = Array.from({ length: 18 }, (_, index) => ({ ...component, id: String(index), slug: `part-${String(index)}` }));
  await mockCatalog(page, editor, items);
  for (const [width, height] of [[1366, 768], [1440, 900], [1920, 1080], [2560, 1440], [1100, 900], [1024, 900], [768, 900], [360, 800], [320, 800]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Каталог компонентов", exact: true })).toBeVisible();
    expect(await page.locator("main").evaluate((main) => main.getBoundingClientRect().width)).toBe(Math.min(width, 2000));
    await expect(page.getByRole("searchbox")).toHaveCount(1);
    await expect(page.getByRole("link", { name: /Добавить компонент/ })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: `/tmp/ackb-catalog-${String(width)}.png` });
    if (width === 1920 || width === 320) {
      await selectTheme(page, "Тёмное");
      await expectNoAccessibilityViolations(page, `workbench ${String(width)} dark`);
      await expectControlTargets(page, `workbench ${String(width)} dark`);
      await page.screenshot({ path: `/tmp/ackb-catalog-${String(width)}-dark.png` });
      await selectTheme(page, "Светлое");
    }
  }
  await page.goto("/about");
  await expect(page.locator("main")).not.toHaveClass(/page--catalog/);
  expect(await page.locator("main").evaluate((main) => main.getBoundingClientRect().width)).toBeLessThanOrEqual(1440);
});

test("compact hardware intro responds to a pointer and respects reduced motion", async ({ page }) => {
  await mockCatalog(page);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const board = page.locator(".hardware-board");
  await expect(board).toHaveAttribute("data-motion", "interactive");
  expect(await page.locator(".catalog-intro").evaluate((element) => element.getBoundingClientRect().height)).toBeLessThanOrEqual(360);
  const bounds = await board.boundingBox();
  if (bounds === null) throw new Error("Board is missing");
  await page.mouse.move(bounds.x + bounds.width * 0.9, bounds.y + bounds.height * 0.1);
  await expect.poll(() => board.evaluate((element) => element.style.getPropertyValue("--board-ry"))).not.toBe("0deg");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(board).toHaveAttribute("data-motion", "static");
  await expect(page.locator(".hardware-board__pcb")).toHaveCSS("transform", "none");
  await page.mouse.move(bounds.x + bounds.width * 0.1, bounds.y + bounds.height * 0.9);
  expect(await board.evaluate((element) => element.style.getPropertyValue("--board-ry"))).toBe("0deg");
});

test("workbench filters stay reachable while scrolling and reset existing API filters", async ({ page }) => {
  const items = Array.from({ length: 18 }, (_, index) => ({ ...component, id: String(index), slug: `part-${String(index)}` }));
  await mockCatalog(page, student, items);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const sidebar = page.getByRole("complementary", { name: "Фильтры компонентов" });
  await expect(sidebar).toBeVisible();
  await page.evaluate(() => { document.body.tabIndex = -1; document.body.focus(); });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "К поиску компонентов" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("searchbox", { name: "Поиск", exact: true })).toBeFocused();
  await expect(sidebar).toHaveCSS("position", "sticky");
  const request = page.waitForRequest((request) => request.url().includes("category_id="));
  await page.getByRole("combobox", { name: "Категория", exact: true }).selectOption(category.id);
  expect((await request).url()).toContain(category.id);
  await page.getByRole("combobox", { name: "Сложность", exact: true }).selectOption("advanced");
  await expect(page.getByLabel("Активные фильтры")).toHaveText("Датчики · Продвинутая");
  await page.getByRole("searchbox", { name: "Поиск", exact: true }).fill("DHT22");
  await expect(page.locator(".catalog-card")).toHaveCount(18);
  await page.evaluate(() => { scrollTo(0, 700); });
  await expect.poll(() => page.evaluate(() => scrollY)).toBeGreaterThan(500);
  await expect(sidebar).toBeVisible();
  const top = await sidebar.evaluate((element) => element.getBoundingClientRect().top);
  expect(top).toBeGreaterThanOrEqual(await page.locator(".topbar").evaluate((element) => element.getBoundingClientRect().bottom));
  await sidebar.getByRole("button", { name: "Сбросить фильтры" }).click();
  await expect(page.getByRole("combobox", { name: "Категория", exact: true })).toHaveValue("");
  await expect(page.getByRole("combobox", { name: "Сложность", exact: true })).toHaveValue("");
  await expect(page.getByRole("searchbox", { name: "Поиск", exact: true })).toHaveValue("");
  await expect(page.getByLabel("Активные фильтры")).toHaveCount(0);
  await page.setViewportSize({ width: 360, height: 800 });
  await expect(sidebar).toHaveCSS("position", "static");
  await expect(page.getByRole("combobox")).toHaveCount(2);
});

test("dense catalog fits six columns at full HD and uses the API result total", async ({ page }) => {
  const items = Array.from({ length: 18 }, (_, index) => ({ ...component, id: String(index), slug: `part-${String(index)}` }));
  await mockCatalog(page, student, items, 83);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await expect(page.locator(".catalog-count")).toHaveText("Найдено: 83");
  const cards = page.locator(".catalog-card");
  await expect(cards).toHaveCount(18);
  const boxes = await cards.evaluateAll((elements) => elements.map((element) => {
    const box = element.getBoundingClientRect();
    return { top: box.top, bottom: box.bottom, width: box.width };
  }));
  expect(boxes.filter((box) => box.top === boxes[0].top)).toHaveLength(6);
  expect(boxes[0].width).toBeGreaterThanOrEqual(240);
  expect(boxes[0].bottom).toBeLessThan(1080);
  await expect(cards.first()).toContainText("3.3–5.5 В");
  await expect(cards.first()).toContainText("GPL-3.0-only");
  await page.screenshot({ path: "/tmp/ackb-dense-1920.png" });
  await page.route("**/api/v1/catalog/components?*", (route) => route.fulfill({ json: { items: [], total: 0 } }));
  await page.getByRole("searchbox", { name: "Поиск", exact: true }).fill("missing");
  await expect(page.locator(".catalog-count")).toHaveText("Найдено: 0");
  await expect(page.getByRole("heading", { name: "Ничего не найдено" })).toBeVisible();
});

test("catalog card content stays inside narrow cards", async ({ page }) => {
  const longCard = {
    ...component,
    id: "30000000-0000-4000-8000-000000000002",
    slug: "long-card",
    title: "Grove-TemperatureSensor-with-a-very-long-name",
    summary: "Precision Thermocouple Amplifiers with Cold Junction Compensation and an exceptionallylongunbrokenidentifier.",
    model: "AD8494-MSOP-8-exceptionallylongunbrokenidentifier",
    tags: ["kicad-symbols-exceptionallylongunbrokenidentifier"],
    sources: [{
      ...component.sources[0],
      license_spdx: "CERN-OHL-W-2.0-exceptionallylongunbrokenidentifier",
    }],
  };
  await mockCatalog(page, student, [component, longCard, { ...longCard, id: "30000000-0000-4000-8000-000000000003", slug: "long-card-copy" }]);

  for (const width of [1024, 320]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.locator(".catalog-card")).toHaveCount(3);
    const overflowing = await page.locator(".catalog-card").evaluateAll((cards) =>
      cards.flatMap((card, cardIndex) =>
        [...card.querySelectorAll<HTMLElement>(
          ".catalog-card__body, .catalog-card__top, h2, p, .tag-list, .tag-list span, .catalog-card__facts, .catalog-card__facts div, dt, dd, footer, footer small",
        )]
          .filter((element) => element.scrollWidth > element.clientWidth + 1)
          .map((element) => `card ${String(cardIndex + 1)}: ${element.tagName.toLowerCase()}.${element.className}`),
      ),
    );
    expect(overflowing, `card content overflow at ${String(width)}px`).toEqual([]);
  }
});

test("student browses the catalog, switches theme and opens sourced learning content", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await mockCatalog(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Каталог компонентов" })).toBeVisible();
  await expect(page.locator(".brand__copy strong")).toHaveText("База компонентов Arduino");
  await expect(page.locator(".brand__copy small")).toHaveText("Справочник электронных компонентов");
  await expect(page.locator(".account__copy strong")).toHaveText("Мария Студентова");
  await expect(page.locator(".account__copy small")).toHaveText("Ученик");
  await expect(page.getByRole("navigation", { name: "Основная навигация" }).getByRole("link"))
    .toHaveText(["Каталог"]);
  const themeTrigger = page.getByRole("button", { name: /^Оформление:/ });
  await expect(themeTrigger).toHaveAttribute("title", "Настроить оформление");
  await expect(themeTrigger).toHaveCSS("height", "44px");
  await expect(themeTrigger).toHaveCSS("width", "44px");
  await expect(page.locator(".hardware-board")).toHaveAttribute("aria-hidden", "true");
  await expect(page.getByText("Источник: Seeed Studio Wiki · GPL-3.0-only")).toBeVisible();
  await expect(page.getByRole("link", { name: /Добавить компонент/ })).toHaveCount(0);
  await expect(page.getByRole("img", { name: "Основной вид DHT22" })).toBeVisible();
  await expectNoAccessibilityViolations(page, "catalog light theme");
  await expectControlTargets(page, "catalog light theme");
  await expectKeyboardFocusVisible(page, "catalog keyboard");
  await selectTheme(page, "Тёмное");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expectNoAccessibilityViolations(page, "catalog dark theme");
  await page.getByRole("link", { name: /Датчик температуры DHT22/ }).click();
  const primaryThumbnail = page.getByRole("button", {
    name: "Показать изображение 1: Основной вид DHT22",
  });
  await primaryThumbnail.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("img", { name: "Разъёмы DHT22" })).toBeVisible();
  await expect(page.getByText("Контакты датчика")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Источник материала" })).toBeVisible();
  const source = page.getByRole("link", { name: /Открыть источник/ });
  await expect(source).toHaveAttribute("target", "_blank");
  await expect(source).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByRole("button", { name: "Показать подсказку 1" }).click();
  await expect(page.getByText("Подключите библиотеку DHT.")).toBeVisible();
  await page.getByRole("button", { name: "Показать решение" }).click();
  await expect(page.locator(".learning-code")).toContainText("Serial.begin");
  await expectNoAccessibilityViolations(page, "component details dark theme");
  await expectControlTargets(page, "component details");
  for (const width of [320, 360, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(
      page.getByRole("navigation", { name: "Основная навигация" }).getByRole("link", {
        name: "Каталог",
      }),
    ).toBeVisible();
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
      `horizontal overflow at ${String(width)}px: ${layout.outsideViewport.join(", ")}`,
    ).toBe(layout.clientWidth);
  }
  await page.goto("/");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".hardware-board__splat")).toHaveCSS("animation-name", "none");
  expect(consoleErrors).toEqual([]);
});

test("editor navigation remains usable at 320px and hides administrator tools", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 900 });
  await mockCatalog(page, editor);
  await page.goto("/admin");

  await expect(page.getByRole("heading", { name: "Обзор материалов" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Основная навигация" }).getByRole("link"))
    .toHaveText(["Каталог", "Редакция"]);
  await expect(page.getByRole("navigation", { name: "Рабочее место редактора" })).toContainText(
    "Загрузка компонентов",
  );
  await expect(page.getByRole("heading", { name: "Администрирование" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Пользователи" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Диагностика" })).toHaveCount(0);
  await page.getByRole("button", { name: /^Оформление:/ }).click();
  await expect(page.getByRole("menu", { name: "Выбор оформления" })).toBeVisible();
  const overflows = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
  );
  expect(overflows).toBe(false);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu", { name: "Выбор оформления" })).toHaveCount(0);
});

test("captures approved responsive theme views", async ({ page }) => {
  test.skip(process.env.ACKB_UPDATE_SCREENSHOTS !== "1", "visual artifacts are updated explicitly");
  const items = Array.from({ length: 12 }, (_, index) => ({ ...component, id: String(index), slug: `part-${String(index)}` }));
  await mockCatalog(page, editor, items);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await selectTheme(page, "Светлое");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-light-desktop.png" });
  await selectTheme(page, "Тёмное");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("heading", { name: "Каталог компонентов" })).toBeVisible();
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-dark-desktop.png" });

  await page.unrouteAll({ behavior: "wait" });
  await mockLoggedOut(page);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/login");
  await selectTheme(page, "Светлое");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-light-mobile.png" });
  await selectTheme(page, "Тёмное");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("heading", { name: "Вход в систему" })).toBeVisible();
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-dark-mobile.png" });
});
