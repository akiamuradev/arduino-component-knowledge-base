import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/query-client";
import { LegacyImportPanel } from "./LegacyImportPanel";

const item = {
  id: "item", decision: "create", status: "planned", result_id: null,
  candidates: [], warnings: [], error_code: null,
  target: { title: "DHT11", category: "ДАТЧИКИ", rows: [116], match: "unmatched",
    folder: null, description: "", specifications: [], images: [], candidates: [], warnings: [] },
};
const initial = { id: "bundle", status: "ready", phase: "analysis", plan_hash: "a".repeat(64),
  statistics: { targets: 1 }, items: [item], error_code: null };

function response(value: unknown) {
  return Promise.resolve(new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } }));
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
}

function mount(path = "/admin/import?legacy=bundle") {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false }, mutations: { retry: false } });
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[path]}>
    <LegacyImportPanel />
  </MemoryRouter></QueryClientProvider>);
}

afterEach(() => { vi.unstubAllGlobals(); document.cookie = "ackb_csrf=; Max-Age=0; Path=/"; });

describe("legacy import human control", () => {
  it("requires exact typed confirmation and sends the current plan hash", async () => {
    document.cookie = "ackb_csrf=fixture; Path=/";
    let status = "ready";
    const fetchMock = vi.fn<typeof fetch>((input, options) => {
      const url = requestUrl(input);
      if (options?.method === "POST") { status = "applying"; return response({ status }); }
      return response(url.endsWith("/legacy-imports") ? [] : { ...initial, status });
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();
    const button = await screen.findByRole("button", { name: "Применить проверенный план" });
    expect(button).toBeDisabled();
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Для применения введите ИМПОРТ"), "импорт");
    expect(button).toBeDisabled();
    await user.clear(screen.getByLabelText("Для применения введите ИМПОРТ"));
    await user.type(screen.getByLabelText("Для применения введите ИМПОРТ"), "ИМПОРТ");
    await user.click(button);
    await waitFor(() => { expect(fetchMock.mock.calls.filter(([, options]) => options?.method === "POST")).toHaveLength(1); });
    const call = fetchMock.mock.calls.find(([, options]) => options?.method === "POST");
    expect(call?.[0]).toBe("/api/v1/legacy-imports/bundle/apply");
    const body = call?.[1]?.body;
    if (typeof body !== "string") throw new Error("Missing JSON request");
    expect(JSON.parse(body)).toEqual({ confirmation: "ИМПОРТ", plan_hash: initial.plan_hash });
  });

  it("does not enable apply while any item still needs review", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>((input) => response(requestUrl(input).endsWith("/legacy-imports")
      ? [] : { ...initial, items: [{ ...item, decision: "review", status: "needs_review" }] })));
    mount();
    await screen.findByText(/Нерешённых позиций: 1/);
    await userEvent.setup().type(screen.getByLabelText("Для применения введите ИМПОРТ"), "ИМПОРТ");
    expect(screen.getByRole("button", { name: "Применить проверенный план" })).toBeDisabled();
  });

  it("rejects an oversized source before creating a server bundle", async () => {
    const fetchMock = vi.fn<typeof fetch>(() => response([]));
    vi.stubGlobal("fetch", fetchMock);
    mount("/admin/import");
    const zip = new File(["zip"], "source.zip", { type: "application/zip" });
    Object.defineProperty(zip, "size", { value: 201 * 1024 * 1024 });
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Исходный ZIP (до 200 МиБ)"), zip);
    await user.upload(screen.getByLabelText("Исходный XLSX (до 64 МиБ)"), new File(["xlsx"], "catalog.xlsx"));
    await user.click(screen.getByRole("button", { name: "Загрузить исходники" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("ZIP до 200 МиБ");
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === "POST")).toBe(false);
  });

  it("uploads both files directly and waits for a separate analyze action", async () => {
    document.cookie = "ackb_csrf=fixture; Path=/";
    const uploads: { method: string; url: string; file?: File }[] = [];
    class UploadRequest {
      status = 200;
      timeout = 0;
      upload = { onprogress: null };
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      ontimeout: (() => void) | null = null;
      open(method: string, url: string) { uploads.push({ method, url }); }
      send(file: File) {
        const current = uploads.at(-1);
        if (!current) throw new Error("Upload was not opened");
        current.file = file;
        queueMicrotask(() => { this.onload?.(); });
      }
    }
    vi.stubGlobal("XMLHttpRequest", UploadRequest);
    let status = "uploading";
    const fetchMock = vi.fn<typeof fetch>((input, options) => {
      const url = requestUrl(input);
      if (url.endsWith("/legacy-imports") && options?.method === "POST") {
        return response({ id: "bundle", uploads: { zip: "/media-storage/private/zip", xlsx: "/media-storage/private/xlsx" } });
      }
      if (url.endsWith("/uploaded")) { status = "uploaded"; return response({ status }); }
      return response(url.endsWith("/legacy-imports") ? [] : { ...initial, status, items: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    mount("/admin/import");
    const user = userEvent.setup();
    await user.upload(screen.getByLabelText("Исходный ZIP (до 200 МиБ)"), new File(["zip"], "source.zip"));
    await user.upload(screen.getByLabelText("Исходный XLSX (до 64 МиБ)"), new File(["xlsx"], "catalog.xlsx"));
    await user.click(screen.getByRole("button", { name: "Загрузить исходники" }));
    await screen.findByRole("button", { name: "Анализировать ZIP + XLSX" });
    expect(uploads.map((upload) => upload.method)).toEqual(["PUT", "PUT"]);
    expect(uploads.map((upload) => upload.file?.name)).toEqual(["source.zip", "catalog.xlsx"]);
    expect(fetchMock.mock.calls.some(([url]) => /\/(apply|analyze)$/.test(requestUrl(url)))).toBe(false);
  });
});
