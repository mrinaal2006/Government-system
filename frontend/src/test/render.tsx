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

export function jsonResponse(body: unknown, status = 200, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

type Routes = Record<string, () => Response | Promise<Response>>;

/** Stub fetch by URL path. Unknown paths fail loudly so tests never hit a network. */
export function mockApi(routes: Routes) {
  const fn = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = new URL(url, "http://localhost").pathname;
    const handler = routes[path];
    if (!handler) throw new Error(`Unmocked API call: ${path}`);
    return handler();
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
