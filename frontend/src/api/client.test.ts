import { afterEach, describe, expect, it, vi } from "vitest";

import { api, apiRequest, uploadReservedFile } from "./client";

afterEach(() => {
  document.cookie = "ackb_csrf=; Max-Age=0; Path=/";
  vi.unstubAllGlobals();
});

describe("apiRequest", () => {
  it("uses same-origin cookies and attaches the CSRF token to mutations", async () => {
    document.cookie = "ackb_csrf=csrf-value; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiRequest<{ status: string }>("/admin/users/user-id/disable", {
      method: "POST",
      csrf: true,
    });

    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/admin/users/user-id/disable");
    expect(options?.credentials).toBe("include");
    expect(new Headers(options?.headers).get("X-CSRF-Token")).toBe("csrf-value");
  });

  it("preserves the unified backend error contract", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "permission_denied",
              message: "Это действие недоступно для вашей роли.",
              retryable: false,
              request_id: "request-1",
            },
          }),
          {
            status: 403,
            headers: { "Content-Type": "application/json" },
          },
        ),
      ),
    );

    await expect(apiRequest("/admin/users")).rejects.toEqual(
      expect.objectContaining({
        status: 403,
        code: "permission_denied",
        message: "Это действие недоступно для вашей роли.",
        retryable: false,
        requestId: "request-1",
      }),
    );
  });

  it("keeps compatibility with the previous typed detail during rollout", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "revision_conflict" } }), {
          status: 409,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(apiRequest("/workspace/components/id")).rejects.toEqual(
      expect.objectContaining({ status: 409, code: "revision_conflict" }),
    );
  });

  it("turns a network failure into a retryable Russian error", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof fetch>().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(apiRequest("/workspace/components")).rejects.toEqual(
      expect.objectContaining({
        status: 0,
        code: "network_unavailable",
        retryable: true,
        message: "Нет связи с сервисом. Проверьте подключение и попробуйте снова.",
      }),
    );
  });

  it("does not expose a malformed non-JSON response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn<typeof fetch>().mockResolvedValue(
        new Response("<h1>PostgreSQL connection traceback</h1>", {
          status: 500,
          headers: { "Content-Type": "text/html" },
        }),
      ),
    );

    await expect(apiRequest("/workspace/components")).rejects.toEqual(
      expect.objectContaining({
        status: 500,
        code: "request_failed",
        message: "Не удалось выполнить запрос.",
      }),
    );
  });

  it("fails closed before a mutation without a CSRF cookie", async () => {
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/auth/logout", { method: "POST", csrf: true })).rejects.toEqual(
      expect.objectContaining({ status: 403, code: "csrf_token_missing" }),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails closed for a malformed encoded CSRF cookie", async () => {
    document.cookie = "ackb_csrf=%E0%A4%A; Path=/";
    const fetchMock = vi.fn<typeof fetch>();
    vi.stubGlobal("fetch", fetchMock);

    await expect(apiRequest("/auth/logout", { method: "POST", csrf: true })).rejects.toEqual(
      expect.objectContaining({ code: "csrf_token_missing" }),
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("protects manual job retry with CSRF", async () => {
    document.cookie = "ackb_csrf=job-csrf; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "job-id", status: "queued" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.retryJob("job-id");

    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/admin/jobs/job-id/retry");
    expect(options?.method).toBe("POST");
    expect(new Headers(options?.headers).get("X-CSRF-Token")).toBe("job-csrf");
  });

  it("protects manual import retry with CSRF", async () => {
    document.cookie = "ackb_csrf=import-csrf; Path=/";
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ id: "import-id", status: "queued" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await api.retryImportJob("import-id");

    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/v1/admin/jobs/imports/import-id/retry");
    expect(options?.method).toBe("POST");
    expect(new Headers(options?.headers).get("X-CSRF-Token")).toBe("import-csrf");
  });

  it("uploads a reserved file without cookies or storage credentials", async () => {
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["image"], "component.png", { type: "image/png" });

    await uploadReservedFile(
      {
        asset_id: "asset-id",
        upload_url: "/media-storage/private/signed-object?signature=placeholder",
        upload_headers: { "Content-Type": "image/png" },
        expires_at: "2026-07-23T10:00:00Z",
        component_revision: 2,
      },
      file,
    );

    const [url, options] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/media-storage/private/signed-object?signature=placeholder");
    expect(options?.method).toBe("PUT");
    expect(options?.credentials).toBe("omit");
    expect(options?.body).toBe(file);
    expect(new Headers(options?.headers).get("Content-Type")).toBe("image/png");
  });
});
