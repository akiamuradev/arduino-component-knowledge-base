import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { CatalogComponent, Category } from "../api/contracts";
import { catalogKeys } from "../catalog/queries";
import { createQueryClient } from "../app/query-client";
import { CatalogComponentPage } from "./CatalogComponentPage";
import { CatalogPage } from "./CatalogPage";

const category: Category = { id: "00000000-0000-0000-0000-000000000020", slug: "sensors", name: "Датчики" };
const card: CatalogComponent = {
  id: "00000000-0000-0000-0000-000000000021", slug: "temperature-sensor",
  title: "Датчик температуры", summary: "Учебная карточка датчика температуры Arduino.",
  primary_category: category, aliases: ["Temperature sensor"], manufacturer: null,
  model: "T-1", tags: ["temperature", "sensor"], description: "Подробное описание.",
  purpose: "Измерение температуры", usage_notes: "Подключите питание.",
  safety_notes: "Проверьте напряжение.", difficulty: "beginner",
  published_at: "2026-07-16T10:00:00Z",
  specifications: [{ key: "supply-voltage", label: "Питание", value_text: "5", value_number: "5", unit: "В", position: 0 }],
  compatibility: [{ target_type: "board", name: "Arduino Uno", version_constraint: null, notes: "Подключение по GPIO", position: 0 }],
  code_examples: [{
    title: "Мигающий светодиод", language: "arduino", practical_task: "Настройте мигание встроенного светодиода.",
    hints: ["Используйте pinMode."], body: "void setup() { pinMode(13, OUTPUT); }", libraries: [],
    explanation: "Пин переводится в режим выхода.", visibility: "student", position: 0,
  }],
  sources: [{
    display_name: "Seeed Studio Wiki", original_url: "https://wiki.seeedstudio.com/Grove-Button/",
    repository_url: "https://github.com/Seeed-Studio/wiki-documents",
    license_name: "GNU General Public License v3.0 only", license_spdx: "GPL-3.0-only",
    license_url: "https://www.gnu.org/licenses/gpl-3.0.html", source_revision: "1234567890abcdef1234567890abcdef12345678",
    source_tag: "docusaurus-version", source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", source_entry_name: null,
    modifications_notice: "Normalized into an educational component draft.", imported_at: "2026-07-15T10:00:00Z",
    attribution: "Based on Seeed Studio Wiki.", parser_name: "seeed_wiki", parser_version: "1.0.0",
  }],
};

function renderCatalog(path = "/") {
  const client = createQueryClient();
  client.setQueryData(catalogKeys.categories, [category]);
  client.setQueryData(catalogKeys.list({ query: "", categoryId: "", difficulty: "" }), { items: [card], total: 1 });
  client.setQueryData(catalogKeys.detail(card.slug), card);
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={<CatalogPage />} /><Route path="/components/:slug" element={<CatalogComponentPage />} /></Routes></MemoryRouter></QueryClientProvider>);
}

describe("student catalog", () => {
  it("renders published cards and accessible filters", async () => {
    renderCatalog();
    expect(await screen.findByRole("link", { name: /Датчик температуры/ })).toHaveAttribute("href", "/components/temperature-sensor");
    expect(screen.getByRole("searchbox", { name: "Поиск" })).toBeVisible();
    expect(screen.getAllByRole("combobox")).toHaveLength(2);
    expect(screen.getByText("Проверенный источник · GPL-3.0-only")).toBeVisible();
  });

  it("renders component details and safety notes", async () => {
    const user = userEvent.setup();
    const view = renderCatalog("/components/temperature-sensor");
    expect(await screen.findByRole("heading", { name: "Датчик температуры", level: 1 })).toBeVisible();
    expect(screen.getByText("Проверьте напряжение.")).toBeVisible();
    expect(screen.getByText("Питание")).toBeVisible();
    expect(screen.getByText("5 В")).toBeVisible();
    expect(screen.getByText(/Плата: Arduino Uno/)).toBeVisible();
    expect(screen.getByRole("heading", { name: "Источник материала" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Открыть источник/ })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("link", { name: /Каталог компонентов/ })).toHaveAttribute("href", "/");
    expect(view.container.querySelector(".learning-code")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Показать подсказку 1" }));
    expect(screen.getByText("Используйте pinMode.")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Показать решение" }));
    expect(view.container.querySelector(".learning-code")).toHaveTextContent("void setup");
  });
});
