/**
 * Navigation. ``permission`` controls visibility only; every API endpoint enforces
 * authorisation independently, so hiding a link is never a security control.
 */

export interface NavItem {
  path: string;
  label: string;
  permission?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  { label: "Overview", items: [{ path: "/", label: "Command dashboard", permission: "dashboard.read" }] },
  {
    label: "Grievances",
    items: [
      { path: "/grievances", label: "Grievance register", permission: "grievance.read" },
      { path: "/grievances/new", label: "Register grievance", permission: "grievance.create" },
      { path: "/intake", label: "Import from sources", permission: "grievance.import" },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { path: "/early-warning", label: "Early warning alerts", permission: "alert.read" },
      { path: "/gis", label: "GIS maps", permission: "gis.read" },
    ],
  },
  {
    label: "Performance",
    items: [
      { path: "/performance", label: "Department performance", permission: "performance.read" },
      { path: "/reports", label: "Reports", permission: "report.generate" },
    ],
  },
  {
    label: "Administration",
    items: [
      { path: "/notifications", label: "Notifications" },
      { path: "/admin/users", label: "Users and roles", permission: "iam.users.read" },
      { path: "/admin/config", label: "Configuration", permission: "config.manage" },
      { path: "/audit", label: "Audit log", permission: "audit.read" },
      { path: "/system-status", label: "System status", permission: "system.read" },
    ],
  },
];

export function visibleGroups(can: (p: string) => boolean): NavGroup[] {
  return NAV_GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => !i.permission || can(i.permission)) })).filter(
    (g) => g.items.length > 0,
  );
}
