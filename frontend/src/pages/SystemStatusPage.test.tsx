import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, READY_OK, renderApp, shellSettled, SYSTEM_INFO } from "@/test/render";

describe("System status page", () => {
  it("shows every component as operational with the check time in IST", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO), "/api/v1/health/ready": () => jsonResponse(READY_OK) });
    renderApp("/system-status");
    await shellSettled();
    expect(await screen.findByText("All services are operational")).toBeInTheDocument();
    expect(screen.getByText(/12:00:00 IST/)).toBeInTheDocument(); // 06:30 UTC = 12:00 IST
    const table = screen.getByRole("table", { name: "Service readiness" });
    expect(within(table).getAllByText("Operational")).toHaveLength(4);
    expect(within(table).getByText("PostGIS spatial extension")).toBeInTheDocument();
  });

  it("explains a degraded dependency from a 503 readiness response", async () => {
    mockApi({
      "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO),
      "/api/v1/health/ready": () =>
        jsonResponse(
          {
            ...READY_OK,
            status: "unavailable",
            components: { ...READY_OK.components, migrations: { status: "unavailable", latency_ms: 2, reason: "schema_not_at_head" } },
          },
          503,
        ),
    });
    renderApp("/system-status");
    await shellSettled();
    expect(await screen.findByRole("alert")).toHaveTextContent("One or more services are unavailable");
    expect(screen.getByText("Database migrations are pending")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
  });

  it("shows an error state with the request reference when the API fails", async () => {
    mockApi({
      "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO),
      "/api/v1/health/ready": () =>
        jsonResponse({ error: { code: "internal_error", message: "An unexpected error occurred.", request_id: "req-777", details: [] } }, 500),
    });
    renderApp("/system-status");
    await shellSettled();
    expect(await screen.findByText("An unexpected error occurred.")).toBeInTheDocument();
    expect(screen.getByText("req-777")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("reports the district as not configured rather than inventing one", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO), "/api/v1/health/ready": () => jsonResponse(READY_OK) });
    renderApp("/system-status");
    await shellSettled();
    expect(await screen.findByText(/Not configured \(set DEPLOYMENT_DISTRICT_NAME\)/)).toBeInTheDocument();
  });
});
