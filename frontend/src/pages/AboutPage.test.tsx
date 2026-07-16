import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PRODUCT_BRAND } from "../config/brand";
import { AboutPage } from "./AboutPage";

describe("about page", () => {
  it("keeps product authorship, license, build data and source policy explicit", () => {
    render(<AboutPage />);
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.productName })).toBeVisible();
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.authorName })).toBeVisible();
    expect(screen.getByRole("heading", { name: PRODUCT_BRAND.licenseName })).toBeVisible();
    expect(screen.getByText(/backend не передал provenance/i)).toBeVisible();
    const repository = screen.getByRole("link", { name: /Официальный репозиторий/ });
    expect(repository).toHaveAttribute("href", PRODUCT_BRAND.officialRepository);
    expect(repository).toHaveAttribute("rel", "noopener noreferrer");
  });
});
