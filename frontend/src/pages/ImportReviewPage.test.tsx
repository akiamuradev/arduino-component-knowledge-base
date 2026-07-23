import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { ImportReviewWorkspace, User } from "../api/contracts";
import { createQueryClient } from "../app/query-client";
import { routes } from "../app/routes";
import { currentUserQueryKey } from "../auth/queries";
import { importReviewKeys } from "../imports/review-queries";
import { ThemeProvider } from "../theme/ThemeProvider";

const admin: User = {
  id: "00000000-0000-0000-0000-000000000001",
  login: "admin",
  display_name: "Administrator",
  roles: ["administrator"],
};

const review: ImportReviewWorkspace = {
  id: "11111111-2222-4333-8444-555555555555",
  status: "pending",
  revision: 3,
  source: { source_key: "seeed_wiki", source_path: "display.md" },
  facts: { profile: "display" },
  provenance: [{ section: "Overview", locator: "display.md:10", parser_version: "2.0.0" }],
  field_confidence: { title: "high", summary: "medium" },
  identity_candidates: [{
    id: "22222222-3333-4444-8555-666666666666",
    selected: true,
    canonical_name: "Grove OLED Display",
    component_kind: "module",
    selected_category: "displays",
    confidence: "high",
    resolution_status: "auto_resolved",
    evidence: { score_breakdown: [{ rule_id: "module_name" }] },
  }],
  quality_report: {
    overall_score_basis_points: 910,
    route: "manual_review",
    issues: [{ code: "quality.enrichment_review_required", severity: "warning" }],
  },
  unmapped_specifications: [{
    key: `spec-${"a".repeat(64)}`,
    original_label: "Display colour",
    original_value: "Blue",
    reason: "taxonomy_alias_missing",
    evidence: [{ section: "Specifications", locator: "display.md:20", parser_version: "2.0.0" }],
    mapped_taxonomy_path: null,
  }],
  conflicts: [{ taxonomy_path: "display.resolution" }],
  enrichments: [{
    id: "33333333-4444-4555-8666-777777777777",
    provider: "kicad",
    external_identity: "Display_Graphic:SSD1306",
    relation_type: "main_integrated_circuit",
    confidence_basis_points: 950,
    status: "suggested",
    evidence: [{ section: "Specifications", locator: "display.md:21", parser_version: "2.0.0" }],
    score_breakdown: [{
      rule_id: "exact_part_number",
      signal: "SSD1306",
      weight_basis_points: 950,
      reason: "Exact evidenced part number",
    }],
    symbol: { symbol_name: "SSD1306" },
    review_reasons: ["internal_relation_requires_review"],
    updated_at: "2026-07-23T12:00:00Z",
  }],
  module_connection: {
    instructions: [{ body: "Connect the module using I2C." }],
    pins: [{ number: "1", name: "VCC", function: "Module supply" }],
  },
  internal_electronic_components: [{
    record_id: "Display_Graphic:SSD1306",
    name: "SSD1306",
    relation_type: "main_integrated_circuit",
    status: "proposed",
  }],
  kicad_symbols: [{
    record_id: "Display_Graphic:SSD1306",
    library: "Display_Graphic",
    symbol_name: "SSD1306",
    footprint_filters: ["Display*"],
    pinout_level: "kicad_symbol",
    pins: [{ number: "4", name: "GND", electrical_type: "power_in" }],
  }],
  parser_issues: [],
  taxonomy_options: ["display.color", "display.resolution"],
  draft: { title: { value: "Grove OLED Display" } },
  audit_trail: [{
    id: "44444444-5555-4666-8777-888888888888",
    actor_id: admin.id,
    action: "parser_issue_marked",
    target_type: "parser_issue",
    target_key: "parser.heading_noise",
    previous_value: {},
    resulting_value: { code: "parser.heading_noise" },
    reason: "Decorative heading",
    review_revision: 2,
    occurred_at: "2026-07-23T12:00:00Z",
  }],
};

function requiredElement(value: HTMLElement | null): HTMLElement {
  if (value === null) throw new Error("Expected review section");
  return value;
}

describe("evidence-first import review", () => {
  it("shows confidence, evidence and three separate hardware levels", async () => {
    const queryClient = createQueryClient();
    queryClient.setDefaultOptions({ queries: { retry: false, staleTime: Infinity } });
    queryClient.setQueryData(currentUserQueryKey, admin);
    queryClient.setQueryData(importReviewKeys.all, { items: [] });
    queryClient.setQueryData(importReviewKeys.detail(review.id), review);
    const router = createMemoryRouter(routes, {
      initialEntries: [`/admin/import-reviews/${review.id}`],
    });
    render(
      <ThemeProvider><QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider></ThemeProvider>,
    );

    expect(
      await screen.findByRole("heading", { name: "Grove OLED Display", level: 2 }),
    ).toBeVisible();
    expect(screen.getByText("quality.enrichment_review_required")).toBeVisible();
    await userEvent.click(screen.getByText("Score breakdown и evidence"));
    expect(screen.getByText(/Exact evidenced part number/)).toBeInTheDocument();
    expect(screen.getByText("Display colour")).toBeVisible();
    expect(screen.getByText(/parser_issue_marked/)).toBeVisible();

    const moduleSection = screen.getByRole("heading", { name: "Подключение модуля" })
      .closest("section");
    const internalSection = screen.getByRole("heading", { name: "Внутренние компоненты" })
      .closest("section");
    const kicadSection = screen.getByRole("heading", { name: "Symbol и footprint KiCad" })
      .closest("section");
    expect(moduleSection).not.toBeNull();
    expect(internalSection).not.toBeNull();
    expect(kicadSection).not.toBeNull();
    expect(within(requiredElement(moduleSection)).getByText("Module supply")).toBeVisible();
    expect(within(requiredElement(moduleSection)).queryByText(/GND/)).not.toBeInTheDocument();
    expect(within(requiredElement(internalSection)).getByText("SSD1306")).toBeVisible();
    expect(
      within(requiredElement(kicadSection)).getByText(
        "Выводы символа KiCad — не pinout модуля",
      ),
    ).toBeInTheDocument();

    const accept = screen.getByRole("button", { name: "Принять enrichment" });
    expect(accept).toBeDisabled();
    await userEvent.type(
      screen.getByRole("textbox", { name: "Основание следующего решения" }),
      "Evidence was checked",
    );
    expect(accept).toBeEnabled();
  });
});
