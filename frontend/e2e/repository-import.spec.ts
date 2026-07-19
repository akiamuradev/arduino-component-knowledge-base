import { expect, test } from "@playwright/test";

const administrator = {
  id: "10000000-0000-4000-8000-000000000001",
  login: "administrator",
  display_name: "Integration Administrator",
  roles: ["administrator"],
};

test("administrator previews a bounded repository entry before creating a draft", async ({ context, page }) => {
  await context.addCookies([{ name: "ackb_csrf", value: "e2e-csrf", url: "http://127.0.0.1:4173" }]);
  let publishCalled = false;
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const json = async (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (path === "/api/v1/auth/me") return json(administrator);
    if (path.endsWith("/repository/discovery")) return json({ source_key: "seeed_wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents", revision: "a".repeat(40), files_scanned: 25, files: [{ file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", size: 2048 }] });
    if (path.endsWith("/repository/entries")) return json({ source_key: "seeed_wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents", revision: "a".repeat(40), entries: [{ file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", entry_name: null, title: "Grove Button" }] });
    if (path.endsWith("/repository/preview")) return json({ source_key: "seeed_wiki", repository_url: "https://github.com/Seeed-Studio/wiki-documents", requested_revision: "docusaurus-version", revision: "a".repeat(40), file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", entry_name: null, original_url: "https://wiki.seeedstudio.com/Grove-Button/", parser_name: "seeed-wiki-git-v1", parser_version: "1.0.0", parse_status: "parsed", warnings: [], normalized_fields: { title: "Grove Button", summary: "Кнопочный модуль", specifications: [] }, provenance: {}, license: { name: "GNU General Public License v3.0 only", spdx: "GPL-3.0-only", url: "https://www.gnu.org/licenses/gpl-3.0.html", attribution: "Seeed Studio Wiki" }, modifications_notice: "Facts extracted and normalized.", draft_status: "draft" });
    if (path === "/api/v1/import-jobs/repository") return json({ id: "40000000-0000-4000-8000-000000000001", submitted_url: "https://github.com/Seeed-Studio/wiki-documents", canonical_url: null, status: "queued", attempts: 0, max_attempts: 4, parser_version: null, draft_component_id: null, error_code: null, repository_url: "https://github.com/Seeed-Studio/wiki-documents", requested_revision: "docusaurus-version", source_revision: null, source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", source_entry_name: null, parser_name: null, parse_status: null, warnings_json: [], heartbeat_at: null, metrics_json: {} });
    if (path === "/api/v1/import-jobs/40000000-0000-4000-8000-000000000001") return json({ id: "40000000-0000-4000-8000-000000000001", submitted_url: "https://github.com/Seeed-Studio/wiki-documents", canonical_url: "https://wiki.seeedstudio.com/Grove-Button/", status: "succeeded", attempts: 1, max_attempts: 4, parser_version: "1.0.0", draft_component_id: "50000000-0000-4000-8000-000000000001", error_code: null, repository_url: "https://github.com/Seeed-Studio/wiki-documents", requested_revision: "docusaurus-version", source_revision: "a".repeat(40), source_file_path: "sites/en/docs/Sensor/Grove/Grove_Button.md", source_entry_name: null, parser_name: "seeed-wiki-git-v1", parse_status: "parsed", warnings_json: [], heartbeat_at: null, metrics_json: {} });
    if (path.includes("publish")) publishCalled = true;
    return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ detail: { code: "unexpected_e2e_request", path } }) });
  });

  await page.goto("/admin/import");
  await page.getByRole("button", { name: "Найти" }).click();
  await page.getByRole("button", { name: /Grove_Button.md/ }).click();
  await page.getByRole("button", { name: /Grove Button/ }).click();
  await page.getByRole("button", { name: "Показать preview" }).click();
  await expect(page.getByRole("heading", { name: "Grove Button" })).toBeVisible();
  await expect(page.getByText("GPL-3.0-only")).toBeVisible();
  await page.getByRole("button", { name: "Создать черновик" }).click();
  await expect(page.getByRole("link", { name: "Открыть draft" })).toHaveAttribute("href", "/admin/components/50000000-0000-4000-8000-000000000001/edit");
  expect(publishCalled).toBe(false);
});
