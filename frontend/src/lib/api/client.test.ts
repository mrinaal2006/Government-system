import { describe, expect, it, vi } from "vitest";

import { jsonResponse } from "@/test/render";

import { ApiError, apiGet } from "./client";

describe("apiGet", () => {
  it("requests same-origin /api/v1 paths with credentials", async () => {
    const fetchMock = vi.fn(async () => jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await apiGet<{ ok: boolean }>("/x");
    expect(result).toEqual({ status: 200, data: { ok: true } });
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/x", expect.objectContaining({ credentials: "same-origin" }));
  });

  it("maps the backend error envelope to ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      jsonResponse({ error: { code: "not_found", message: "Missing", request_id: "rid-1", details: [] } }, 404),
    ));
    await expect(apiGet("/x")).rejects.toMatchObject({ name: "ApiError", status: 404, code: "not_found", requestId: "rid-1" });
  });

  it("returns accepted non-2xx statuses as results", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ status: "unavailable" }, 503)));
    await expect(apiGet("/health/ready", { acceptStatuses: [503] })).resolves.toEqual({ status: 503, data: { status: "unavailable" } });
  });

  it("reports network failures without leaking internals", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const err = await apiGet("/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("network_error");
  });

  it("handles non-JSON error bodies (e.g. proxy pages)", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>Bad gateway</html>", { status: 502, headers: { "content-type": "text/html", "x-request-id": "r2" } })));
    await expect(apiGet("/x")).rejects.toMatchObject({ status: 502, code: "http_error", requestId: "r2" });
  });
});
