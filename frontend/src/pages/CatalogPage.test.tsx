import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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
  });

  it("renders component details and safety notes", async () => {
    renderCatalog("/components/temperature-sensor");
    expect(await screen.findByRole("heading", { name: "Датчик температуры", level: 1 })).toBeVisible();
    expect(screen.getByText("Проверьте напряжение.")).toBeVisible();
    expect(screen.getByRole("link", { name: /К каталогу/ })).toHaveAttribute("href", "/");
  });
});
