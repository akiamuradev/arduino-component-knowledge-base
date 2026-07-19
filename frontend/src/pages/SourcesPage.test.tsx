import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { CatalogSource } from "../api/contracts";
import { createQueryClient } from "../app/query-client";
import { catalogKeys } from "../catalog/queries";
import { SourcesPage } from "./SourcesPage";

const active: CatalogSource = {
  key: "seeed_wiki", display_name: "Seeed Studio Wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents",
  source_type: "git_repository", status: "active", content_policy: "licensed_content",
  license_name: "GNU General Public License v3.0 only", license_spdx: "GPL-3.0-only", license_url: "https://www.gnu.org/licenses/gpl-3.0.html",
  attribution_template: "Seeed Studio Wiki", adapter_version: "1.0.0", default_revision_policy: "pinned_tag", disable_reason: null,
};

describe("sources registry", () => {
  it("separates active sources and owner-denied historical records", () => {
    const client = createQueryClient();
    client.setQueryData(catalogKeys.sources, [active, {
      ...active, key: "alexgyver", display_name: "AlexGyver", repository_url: null,
      status: "disabled", license_name: null, license_spdx: null, license_url: null,
      attribution_template: null, disable_reason: "owner_denied_usage",
    }]);
    render(<QueryClientProvider client={client}><MemoryRouter><SourcesPage /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByRole("heading", { name: "Активные источники" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "Неактивные источники" })).toBeVisible();
    expect(screen.getByText("Использование запрещено владельцем источника.")).toBeVisible();
    expect(screen.getByRole("link", { name: /Официальный repository/ })).toHaveAttribute("rel", "noopener noreferrer");
  });
});
