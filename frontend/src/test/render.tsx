import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { vi } from "vitest";

import { AppProviders, createQueryClient } from "@/app/providers";
import { buildRoutes } from "@/app/routes";

export const SYSTEM_INFO = {
  application: "DG-IMEWS",
  version: "0.1.0",
  environment: "development",
  deployment: { district_name: null, district_name_local: null, state_name: null, state_name_local: null },
};

export const READY_OK = {
  status: "ok",
  checked_at: "2026-10-31T06:30:00+00:00",
  components: {
    database: { status: "ok", latency_ms: 1.2, reason: null },
    postgis: { status: "ok", latency_ms: 0.8, reason: null },
    migrations: { status: "ok", latency_ms: 0.9, reason: null },
    redis: { status: "ok", latency_ms: 0.4, reason: null },
  },
};

export const DM_PERMISSIONS = [
  "grievance.read", "grievance.create", "grievance.update", "grievance.assign", "grievance.work", "grievance.verify",
  "grievance.reopen", "grievance.escalate", "grievance.comment", "grievance.attach", "grievance.link", "citizen.read",
  "ai.read", "ai.review", "alert.read", "alert.act", "gis.read", "gis.read_precise", "dashboard.read", "performance.read",
  "report.generate", "report.export", "audit.read", "iam.users.read", "system.read",
];
export const OFFICER_PERMISSIONS = ["grievance.read", "grievance.work", "grievance.comment", "grievance.attach", "citizen.read", "ai.read", "system.read"];

export function session(permissions: string[] = DM_PERMISSIONS, roles = ["district_magistrate"], state = "authenticated") {
  return { state, user: { id: "u1", username: "test.user", full_name: "Test Officer", roles, permissions, mfa_enrolled: true } };
}

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

type Routes = Record<string, (url: URL, init?: RequestInit) => Response | Promise<Response>>;

const EMPTY_PAGE = { items: [], total: 0, limit: 25, offset: 0 };

/** Defaults so pages render; tests override what they assert on. Unknown paths fail loudly. */
export function defaultRoutes(perms: string[] = DM_PERMISSIONS): Routes {
  return {
    "/api/v1/auth/me": () => jsonResponse(session(perms)),
    "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO),
    "/api/v1/health/ready": () => jsonResponse(READY_OK),
    "/api/v1/notifications": () => jsonResponse({ items: [], total: 0, unread: 0 }),
    "/api/v1/dashboard/summary": () => jsonResponse({ generated_at: "2026-10-31T06:30:00+00:00", kpis: [
      { key: "total", label: "Total grievances", value: 12, filter: {} },
      { key: "overdue", label: "Overdue", value: 3, filter: { overdue: true } },
    ] }),
    "/api/v1/dashboard/trends": () => jsonResponse({ series: [] }),
    "/api/v1/dashboard/blocks": () => jsonResponse([]),
    "/api/v1/dashboard/categories": () => jsonResponse([]),
    "/api/v1/dashboard/clusters": () => jsonResponse([]),
    "/api/v1/dashboard/important": () => jsonResponse([]),
    "/api/v1/dashboard/recent-actions": () => jsonResponse([]),
    "/api/v1/performance/departments": () => jsonResponse([]),
    "/api/v1/grievances": () => jsonResponse(EMPTY_PAGE),
    "/api/v1/reference/sources": () => jsonResponse([{ id: "s1", code: "MANUAL", name_en: "Manual submission", is_active: true }]),
    "/api/v1/reference/departments": () => jsonResponse([]),
    "/api/v1/reference/categories": () => jsonResponse([]),
    "/api/v1/reference/units/districts": () => jsonResponse([]),
    "/api/v1/reference/units/blocks": () => jsonResponse([]),
    "/api/v1/reference/units/municipalities": () => jsonResponse([]),
    "/api/v1/auth/signup/options": () => jsonResponse({ officer_signup_enabled: true, citizen_portal_enabled: true }),
  };
}

export function mockApi(routes: Routes = {}, perms?: string[]) {
  const all = { ...defaultRoutes(perms), ...routes };
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://localhost");
    const handler = all[url.pathname];
    if (!handler) throw new Error(`Unmocked API call: ${url.pathname}`);
    return handler(url, init);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function renderApp(path = "/") {
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false, refetchInterval: false } });
  const router = createMemoryRouter(buildRoutes({ includeDevRoutes: true }), { initialEntries: [path] });
  return {
    router,
    ...render(
      <AppProviders client={client}>
        <RouterProvider router={router} />
      </AppProviders>,
    ),
  };
}

/** Wait until the shell's deployment metadata has loaded (avoids act() warnings). */
export async function shellSettled() {
  await screen.findByText(/DG-IMEWS version/);
}
