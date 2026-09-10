import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PRODUCT_BRAND } from "../config/brand";
import { AppFooter } from "../components/AppFooter";
import { AboutPage } from "./AboutPage";

describe("about page", () => {
  it("shows the same license and author in the site footer", () => {
    render(<MemoryRouter><AppFooter /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "GNU GPL v3.0 или новее" })).toHaveAttribute("href", "/LICENCE.txt");
    expect(screen.getByRole("link", { name: "akiamuradev" })).toHaveAttribute("href", "https://github.com/akiamuradev");
  });
  it("keeps product authorship, license, build data and source policy explicit", () => {
    render(<MemoryRouter><AboutPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.productName })).toBeVisible();
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.authorName })).toBeVisible();
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.licenseName })).toBeVisible();
    expect(PRODUCT_BRAND.authorName).toBe("akiamuradev");
    expect(PRODUCT_BRAND.licenseName).toBe("GNU GPL v3.0 или новее");
    expect(PRODUCT_BRAND.licenseSpdx).toBe("GPL-3.0-or-later");
    expect(screen.getByRole("link", { name: /Открыть текст лицензии/ })).toHaveAttribute("href", "/LICENCE.txt");
    expect(screen.getByText(/подтверждённый снимок источника отсутствует/i)).toBeVisible();
    expect(screen.getByText(/Seeed Studio Wiki и официальные библиотеки KiCad/i)).toBeVisible();
    expect(screen.getByText(/все зарегистрированные источники неактивны/i)).toBeVisible();
    expect(screen.queryByText(/Действующие источники:/)).not.toBeInTheDocument();
    const repository = screen.getByRole("link", { name: /Официальный репозиторий/ });
    expect(repository).toHaveAttribute("href", PRODUCT_BRAND.officialRepository);
    expect(repository).toHaveAttribute("rel", "noopener noreferrer");
  });
});
