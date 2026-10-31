/**
 * Single source of truth for navigation and module routes.
 *
 * Visibility here is presentation only. From Phase 2 the sidebar will hide items
 * the user lacks permission for, but every API endpoint enforces authorisation
 * independently; hiding a link is never a security control.
 */

export interface ModuleDefinition {
  path: string;
  label: string;
  /** Development phase in which the module becomes functional; undefined = available. */
  phase?: number;
  summary: string;
}

export interface NavGroup {
  label: string;
  items: ModuleDefinition[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { path: "/", label: "Command dashboard", phase: 3, summary: "District-wide KPIs, trends, alerts and important unresolved grievances, computed from live records." },
    ],
  },
  {
    label: "Grievances",
    items: [
      { path: "/grievances", label: "Grievance register", phase: 4, summary: "Search, filter and act on grievances within your authorised scope." },
      { path: "/grievances/new", label: "Register grievance", phase: 4, summary: "Record a new grievance with source, location, category and attachments." },
    ],
  },
  {
    label: "Intelligence",
    items: [
      { path: "/early-warning", label: "Early warning alerts", phase: 6, summary: "Explainable risk alerts with reasons, evidence and recommended administrative actions." },
      { path: "/gis", label: "GIS maps", phase: 6, summary: "Hotspots and clusters on verified administrative boundaries." },
    ],
  },
  {
    label: "Performance",
    items: [
      { path: "/performance", label: "Department performance", phase: 7, summary: "SLA compliance, escalations and block-level performance." },
      { path: "/reports", label: "Reports", phase: 8, summary: "PDF and Excel reports, trend analysis and executive summaries." },
    ],
  },
  {
    label: "Administration",
    items: [
      { path: "/notifications", label: "Notifications", phase: 3, summary: "Notification centre for assignments, escalations and alerts." },
      { path: "/administration", label: "Configuration", phase: 3, summary: "Departments, issue categories, grievance sources and administrative geography." },
      { path: "/audit", label: "Audit log", phase: 2, summary: "Tamper-evident record of security and administrative actions." },
      { path: "/system-status", label: "System status", summary: "Live readiness of the database, PostGIS, migrations and Redis." },
    ],
  },
];

export const MODULES: ModuleDefinition[] = NAV_GROUPS.flatMap((g) => g.items);
