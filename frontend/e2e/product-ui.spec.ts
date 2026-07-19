import { expect, type Page, test } from "@playwright/test";

const student = {
  id: "10000000-0000-4000-8000-000000000002",
  login: "student",
  display_name: "Мария Студентова",
  roles: ["student"],
};

const category = { id: "20000000-0000-4000-8000-000000000001", slug: "sensors", name: "Датчики" };
const component = {
  id: "30000000-0000-4000-8000-000000000001",
  slug: "dht22",
  title: "Датчик температуры DHT22",
  summary: "Цифровой датчик температуры и влажности для учебных Arduino-проектов.",
  primary_category: category,
  aliases: ["AM2302"],
  manufacturer: "Aosong",
  model: "DHT22",
  tags: ["температура", "влажность", "digital"],
  description: "DHT22 измеряет температуру и относительную влажность и передаёт данные по однопроводному цифровому интерфейсу.",
  purpose: "Измерение параметров микроклимата в учебных проектах.",
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
  sources: [{
    display_name: "Seeed Studio Wiki", original_url: "https://wiki.seeedstudio.com/Grove-Temperature_And_Humidity_Sensor_Pro/",
    repository_url: "https://github.com/Seeed-Studio/wiki-documents", license_name: "GNU General Public License v3.0 only",
    license_spdx: "GPL-3.0-only", license_url: "https://www.gnu.org/licenses/gpl-3.0.html", source_revision: "1234567890abcdef1234567890abcdef12345678",
    source_tag: "docusaurus-version", source_file_path: "sites/en/docs/Sensor/Grove/Grove-Temperature_And_Humidity_Sensor_Pro.md", source_entry_name: null,
    modifications_notice: "Facts extracted and normalized.", imported_at: "2026-07-15T10:00:00Z", attribution: "Based on Seeed Studio Wiki.",
    parser_name: "seeed-wiki-git-v1", parser_version: "1.0.0",
  }],
};

async function mockCatalog(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(student) });
      return;
    }
    if (path === "/api/v1/catalog/categories") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify([category]) });
      return;
    }
    if (path === "/api/v1/catalog/components") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ items: [component], total: 1 }) });
      return;
    }
    if (path === "/api/v1/catalog/components/dht22") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(component) });
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

test("student browses the catalog, switches theme and opens sourced learning content", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await mockCatalog(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Исследуйте мир Arduino-компонентов" })).toBeVisible();
  await expect(page.locator(".hero__splat")).toHaveAttribute("aria-hidden", "true");
  await expect(page.getByText("Проверенный источник · GPL-3.0-only")).toBeVisible();
  await expect(page.getByRole("link", { name: /Добавить компонент/ })).toHaveCount(0);
  await page.keyboard.press("Tab");
  await expect(page.locator(":focus")).toBeVisible();
  await page.getByRole("button", { name: "Тёмная тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: /Датчик температуры DHT22/ }).click();
  await expect(page.getByRole("heading", { name: "Источник материала" })).toBeVisible();
  const source = page.getByRole("link", { name: /Открыть источник/ });
  await expect(source).toHaveAttribute("target", "_blank");
  await expect(source).toHaveAttribute("rel", "noopener noreferrer");
  await page.getByRole("button", { name: "Показать подсказку 1" }).click();
  await expect(page.getByText("Подключите библиотеку DHT.")).toBeVisible();
  await page.getByRole("button", { name: "Показать решение" }).click();
  await expect(page.locator(".learning-code")).toContainText("Serial.begin");
  for (const width of [360, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    expect(overflows, `horizontal overflow at ${String(width)}px`).toBe(false);
  }
  await page.goto("/");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.locator(".brand-splat--animated").first()).toHaveCSS("animation-name", "none");
  expect(consoleErrors).toEqual([]);
});

test("captures approved responsive theme views", async ({ page }) => {
  test.skip(process.env.ACKB_UPDATE_SCREENSHOTS !== "1", "visual artifacts are updated explicitly");
  await mockCatalog(page);
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await page.getByRole("button", { name: "Светлая тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-light-desktop.png" });
  await page.getByRole("button", { name: "Тёмная тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-dark-desktop.png" });

  await page.unrouteAll({ behavior: "wait" });
  await mockLoggedOut(page);
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto("/login");
  await page.getByRole("radio", { name: /Студент/ }).click();
  await page.getByRole("button", { name: "Светлая тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-light-mobile.png" });
  await page.getByRole("button", { name: "Тёмная тема" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await page.getByRole("radio", { name: /Студент/ }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.screenshot({ fullPage: true, path: "../docs/screenshots/frontend-dark-mobile.png" });
});
