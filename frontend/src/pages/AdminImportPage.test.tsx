import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/query-client";
import { AdminImportPage } from "./AdminImportPage";

function response(value: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } }));
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  return input instanceof URL ? input.href : input.url;
}

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("repository import workspace", () => {
  it("requires preview before it creates a draft-only background job", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const fetchMock = vi.fn<typeof fetch>((input, init) => {
      const url = requestUrl(input);
      if (url.includes("/repository/discovery?")) return response({
        source_key: "seeed_wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents",
        revision: "a".repeat(40), files_scanned: 25,
        files: [{ file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", size: 2048 }],
      });
      if (url.includes("/repository/entries?")) return response({
        source_key: "seeed_wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents",
        revision: "a".repeat(40), entries: [{ file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", entry_name: null, title: "Grove Button" }],
      });
      if (url.endsWith("/repository/preview")) return response({
        source_key: "seeed_wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents",
        requested_revision: "docusaurus-version", revision: "a".repeat(40),
        file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", entry_name: null,
        original_url: "https://wiki.seeedstudio.com/Grove-Button/", parser_name: "seeed-wiki-git-v1", parser_version: "1.0.0",
        parse_status: "parsed_with_warnings", warnings: ["manual_review_required"],
        normalized_fields: { title: "Grove Button", summary: "Кнопочный модуль", specifications: [] },
        provenance: { title: [{ repository_url: "https://github.com/Seeed-Studio/wiki-documents", source_revision: "a".repeat(40), source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", section_or_property: "title", confidence: "high", transformation: "normalized" }] },
        license: { name: "GNU General Public License v3.0 only", spdx: "GPL-3.0-only", url: "https://www.gnu.org/licenses/gpl-3.0.html", attribution: "Seeed Studio Wiki" },
        modifications_notice: "Facts extracted and normalized.", draft_status: "draft",
      });
      if (url.endsWith("/import-jobs/repository") && init?.method === "POST") return response({
        id: "00000000-0000-0000-0000-000000000099", submitted_url: "https://github.com/Seeed-Studio/wiki-documents", canonical_url: null,
        status: "queued", attempts: 0, max_attempts: 4, parser_version: null, draft_component_id: null, error_code: null,
        repository_url: "https://github.com/Seeed-Studio/wiki-documents", requested_revision: "docusaurus-version", source_revision: null,
        source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", source_entry_name: null, parser_name: null, parse_status: null,
        warnings_json: [], heartbeat_at: null, metrics_json: {},
      });
      if (url.includes("/import-jobs/00000000-0000-0000-0000-000000000099")) return response({
        id: "00000000-0000-0000-0000-000000000099", submitted_url: "https://github.com/Seeed-Studio/wiki-documents", canonical_url: "https://wiki.seeedstudio.com/Grove-Button/",
        status: "succeeded", attempts: 1, max_attempts: 4, parser_version: "1.0.0", draft_component_id: "00000000-0000-0000-0000-000000000100", error_code: null,
        repository_url: "https://github.com/Seeed-Studio/wiki-documents", requested_revision: "docusaurus-version", source_revision: "a".repeat(40),
        source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", source_entry_name: null, parser_name: "seeed-wiki-git-v1", parse_status: "parsed_with_warnings",
        warnings_json: ["manual_review_required"], heartbeat_at: null, metrics_json: {},
      });
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = createQueryClient();
    client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
    render(<QueryClientProvider client={client}><MemoryRouter><AdminImportPage /></MemoryRouter></QueryClientProvider>);
    const user = userEvent.setup();

    expect(screen.getByRole("button", { name: "Создать черновик" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Найти" }));
    await user.click(await screen.findByRole("button", { name: /Grove_Button.md/ }));
    await user.click(await screen.findByRole("button", { name: /Grove Button/ }));
    await user.click(screen.getByRole("button", { name: "Показать preview" }));
    expect(await screen.findByRole("heading", { name: "Grove Button" })).toBeVisible();
    expect(screen.getByText("GPL-3.0-only")).toBeVisible();
    expect(screen.getByText("manual_review_required")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Создать черновик" }));
    expect(await screen.findByRole("link", { name: "Открыть draft" })).toHaveAttribute("href", "/admin/components/00000000-0000-0000-0000-000000000100/edit");
    await waitFor(() => { expect(fetchMock).toHaveBeenCalledTimes(5); });
    expect(fetchMock.mock.calls.some(([request]) => requestUrl(request).includes("publish"))).toBe(false);
  });
});
