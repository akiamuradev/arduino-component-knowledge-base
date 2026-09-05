import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { PRODUCT_BRAND } from "../config/brand";
import { AboutPage } from "./AboutPage";

describe("about page", () => {
  it("keeps product authorship, license, build data and source policy explicit", () => {
    render(<MemoryRouter><AboutPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.productName })).toBeVisible();
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.authorName })).toBeVisible();
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.licenseName })).toBeVisible();
    expect(screen.getByText(/подтверждённый снимок источника отсутствует/i)).toBeVisible();
    expect(screen.getByText(/Seeed Studio Wiki и официальные библиотеки KiCad/i)).toBeVisible();
    expect(screen.getByText(/Текущий статус каждого источника указан в реестре/)).toBeVisible();
    expect(screen.queryByText(/Действующие источники:/)).not.toBeInTheDocument();
    const repository = screen.getByRole("link", { name: /Официальный репозиторий/ });
    expect(repository).toHaveAttribute("href", PRODUCT_BRAND.officialRepository);
    expect(repository).toHaveAttribute("rel", "noopener noreferrer");
  });
});
