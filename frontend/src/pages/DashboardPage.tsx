import { Link } from "react-router";

import { Alert, EmptyState, PageHeader } from "@/design-system";

/**
 * Phase 1 placeholder. The command dashboard (Phase 3) computes every KPI from
 * backend queries, and each KPI links to its filtered records. Until then, no
 * figures are displayed: decorative or sample numbers are prohibited.
 */
export function DashboardPage() {
  return (
    <>
      <PageHeader
        title="District command dashboard"
        description="District-wide view of grievances, alerts, trends and department performance."
      />
      <div className="grid grid-cols-1 gap-5">
        <Alert tone="info" title="The command dashboard is delivered in Phase 3">
          Indicators will be computed only from live grievance records. No figures are shown until then.
        </Alert>
        <EmptyState title="No dashboard indicators yet" action={<Link to="/system-status">View system status</Link>}>
          The platform foundation is in place: database, spatial extension, background processing and this interface.
        </EmptyState>
      </div>
    </>
  );
}
