import type { ReactNode } from "react";
import type { RouteObject } from "react-router";

import { RequireAuth, RequirePermission } from "@/app/guards";
import { AppShell, type RouteHandle } from "@/layout/AppShell";
import { AccessibilityPage } from "@/pages/AccessibilityPage";
import { AuditPage } from "@/pages/admin/AuditPage";
import { ConfigPage } from "@/pages/admin/ConfigPage";
import { UsersPage } from "@/pages/admin/UsersPage";
import { AlertDetailPage, AlertsPage } from "@/pages/AlertsPages";
import { LoginPage } from "@/pages/auth/LoginPage";
import { SignUpPage } from "@/pages/auth/SignUpPage";
import { ChangePasswordPage, MfaSetupPage, MfaVerifyPage } from "@/pages/auth/MfaPages";
import {
  CitizenGrievanceDetailPage,
  CitizenHomePage,
  CitizenLayout,
  CitizenLoginPage,
  CitizenNewGrievancePage,
  CitizenRegisterPage,
  CitizenVerifyPage,
} from "@/pages/citizen/CitizenPortal";
import { HomePage } from "@/pages/DashboardPage";
import { DesignSystemPage } from "@/pages/DesignSystemPage";
import { GisPage } from "@/pages/GisPage";
import { GrievanceDetailPage } from "@/pages/grievances/GrievanceDetailPage";
import { GrievanceListPage } from "@/pages/grievances/GrievanceListPage";
import { GrievanceRegisterPage } from "@/pages/grievances/GrievanceRegisterPage";
import { IntakePage } from "@/pages/IntakePage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { NotificationsPage } from "@/pages/NotificationsPage";
import { PerformancePage } from "@/pages/PerformancePage";
import { ReportsPage } from "@/pages/ReportsPage";
import { SystemStatusPage } from "@/pages/SystemStatusPage";

const HOME = { label: "Home", to: "/" };

function handle(title: string, parent?: { label: string; to: string }): RouteHandle {
  return { title, crumbs: [HOME, ...(parent ? [parent] : []), { label: title }] };
}

function guarded(path: string, el: ReactNode, title: string, perms: string[], parent?: { label: string; to: string }): RouteObject {
  return { path, element: perms.length ? <RequirePermission all={perms}>{el}</RequirePermission> : el, handle: handle(title, parent) };
}

const GRIEVANCES = { label: "Grievance register", to: "/grievances" };
const ALERTS = { label: "Early warning alerts", to: "/early-warning" };

export function buildRoutes({ includeDevRoutes }: { includeDevRoutes: boolean }): RouteObject[] {
  return [
    { path: "/login", element: <LoginPage />, handle: { title: "Sign in" } },
    { path: "/login/verify", element: <MfaVerifyPage />, handle: { title: "Verify identity" } },
    { path: "/login/setup-mfa", element: <MfaSetupPage />, handle: { title: "Set up MFA" } },
    { path: "/login/change-password", element: <ChangePasswordPage />, handle: { title: "Change password" } },
    { path: "/signup", element: <SignUpPage />, handle: { title: "Sign up" } },
    {
      path: "/citizen",
      element: <CitizenLayout />,
      children: [
        { index: true, element: <CitizenHomePage />, handle: { title: "Citizen portal" } },
        { path: "register", element: <CitizenRegisterPage />, handle: { title: "Create an account" } },
        { path: "verify", element: <CitizenVerifyPage />, handle: { title: "Verify mobile number" } },
        { path: "login", element: <CitizenLoginPage />, handle: { title: "Citizen sign in" } },
        { path: "new", element: <CitizenNewGrievancePage />, handle: { title: "File a grievance" } },
        { path: "grievances/:id", element: <CitizenGrievanceDetailPage />, handle: { title: "My grievance" } },
        { path: "*", element: <NotFoundPage />, handle: { title: "Page not found" } },
      ],
    },
    {
      path: "/",
      element: (
        <RequireAuth>
          <AppShell />
        </RequireAuth>
      ),
      children: [
        { index: true, element: <HomePage />, handle: { title: "Command dashboard", crumbs: [] } },
        guarded("grievances", <GrievanceListPage />, "Grievance register", ["grievance.read"]),
        guarded("grievances/new", <GrievanceRegisterPage />, "Register grievance", ["grievance.create"], GRIEVANCES),
        guarded("grievances/:id", <GrievanceDetailPage />, "Grievance details", ["grievance.read"], GRIEVANCES),
        guarded("intake", <IntakePage />, "Import from sources", ["grievance.import"]),
        guarded("early-warning", <AlertsPage />, "Early warning alerts", ["alert.read"]),
        guarded("early-warning/:id", <AlertDetailPage />, "Alert details", ["alert.read"], ALERTS),
        guarded("gis", <GisPage />, "GIS maps", ["gis.read"]),
        guarded("performance", <PerformancePage />, "Department performance", ["performance.read"]),
        guarded("reports", <ReportsPage />, "Reports", ["report.generate"]),
        guarded("notifications", <NotificationsPage />, "Notifications", []),
        guarded("admin/users", <UsersPage />, "Users and roles", ["iam.users.read"]),
        guarded("admin/config", <ConfigPage />, "Configuration", ["config.manage"]),
        guarded("audit", <AuditPage />, "Audit log", ["audit.read"]),
        guarded("system-status", <SystemStatusPage />, "System status", ["system.read"]),
        guarded("account/password", <ChangePasswordPage />, "Change password", []),
        { path: "accessibility", element: <AccessibilityPage />, handle: handle("Accessibility statement") },
        ...(includeDevRoutes && import.meta.env.DEV
          ? [{ path: "design-system", element: <DesignSystemPage />, handle: handle("Design system reference") }]
          : []),
        { path: "*", element: <NotFoundPage />, handle: handle("Page not found") },
      ],
    },
  ];
}
