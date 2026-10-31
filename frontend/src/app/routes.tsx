import type { RouteObject } from "react-router";

import { AppShell, type RouteHandle } from "@/layout/AppShell";
import { MODULES } from "@/layout/navigation";
import { AccessibilityPage } from "@/pages/AccessibilityPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DesignSystemPage } from "@/pages/DesignSystemPage";
import { ModulePlaceholderPage } from "@/pages/ModulePlaceholderPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SystemStatusPage } from "@/pages/SystemStatusPage";

const HOME = { label: "Home", to: "/" };

function handle(title: string, parent?: { label: string; to: string }): RouteHandle {
  return { title, crumbs: [HOME, ...(parent ? [parent] : []), { label: title }] };
}

const placeholderRoutes: RouteObject[] = MODULES.filter((m) => m.phase && m.path !== "/").map((m) => ({
  path: m.path.slice(1),
  element: <ModulePlaceholderPage module={m} />,
  handle: handle(m.label, m.path === "/grievances/new" ? { label: "Grievance register", to: "/grievances" } : undefined),
}));

export function buildRoutes({ includeDevRoutes }: { includeDevRoutes: boolean }): RouteObject[] {
  return [
    {
      path: "/",
      element: <AppShell />,
      children: [
        { index: true, element: <DashboardPage />, handle: { title: "Command dashboard", crumbs: [] } },
        ...placeholderRoutes,
        { path: "system-status", element: <SystemStatusPage />, handle: handle("System status") },
        { path: "accessibility", element: <AccessibilityPage />, handle: handle("Accessibility statement") },
        ...(includeDevRoutes && import.meta.env.DEV
          ? [{ path: "design-system", element: <DesignSystemPage />, handle: handle("Design system reference") }]
          : []),
        { path: "*", element: <NotFoundPage />, handle: handle("Page not found") },
      ],
    },
  ];
}
