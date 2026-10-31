import { useState } from "react";
import { Link } from "react-router";

import { Chart, DataTable, PageHeader, Panel, Tabs, TextField } from "@/design-system";
import { formatShortIST, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { useCategories } from "@/lib/reference";

interface Row { id: string | null; name: string; received: number; open: number; resolved: number; overdue: number; within_sla: number; sla_compliance_pct: number | null; resolution_rate_pct: number | null; avg_hours: number | null; reopened: number; escalated: number }
interface Esc { grievance_id: string; reference_no: string; subject: string; level: number; trigger: string; reason: string; created_at: string }
interface Sla { id: string; name: string; category_id: string | null; priority: string | null; resolution_hours: number; warning_percent: number; legal_reference: string | null; is_active: boolean }

function PerfTable({ rows, loading, caption, filterKey }: { rows: Row[] | undefined; loading: boolean; caption: string; filterKey: string }) {
  return (
    <DataTable<Row> caption={caption} rows={rows} rowKey={(r) => r.id ?? "none"} loading={loading} emptyTitle="No grievances in this period"
      columns={[
        { key: "n", header: caption.split(" ")[0] ?? "Name", render: (r) => (r.id ? <Link to={`/grievances?${filterKey}=${r.id}`}>{r.name}</Link> : r.name) },
        { key: "r", header: "Received", align: "right", render: (r) => r.received },
        { key: "o", header: "Open", align: "right", render: (r) => r.open },
        { key: "res", header: "Resolved", align: "right", render: (r) => r.resolved },
        { key: "od", header: "Overdue", align: "right", render: (r) => (r.id ? <Link to={`/grievances?${filterKey}=${r.id}&overdue=true`}>{r.overdue}</Link> : r.overdue) },
        { key: "sla", header: "Within time limit", align: "right", render: (r) => (r.sla_compliance_pct === null ? "n/a" : `${r.sla_compliance_pct}%`) },
        { key: "rate", header: "Resolution rate", align: "right", render: (r) => (r.resolution_rate_pct === null ? "n/a" : `${r.resolution_rate_pct}%`) },
        { key: "avg", header: "Avg. time", align: "right", render: (r) => (r.avg_hours === null ? "n/a" : `${r.avg_hours} h`) },
        { key: "re", header: "Reopened", align: "right", render: (r) => r.reopened },
        { key: "e", header: "Escalated", align: "right", render: (r) => r.escalated },
      ]} />
  );
}

export function PerformancePage() {
  const [tab, setTab] = useState("departments");
  const [since, setSince] = useState("");
  const params = { since: since ? new Date(since).toISOString() : undefined };
  const deps = useApi<Row[]>("/performance/departments", params);
  const blocks = useApi<Row[]>("/performance/blocks", params);
  const esc = useApi<Esc[]>("/performance/escalations", { days: 30 });
  const sla = useApi<Sla[]>("/admin/sla-policies");
  const cats = useCategories();
  const catName = (id: string | null) => cats.data?.find((c) => c.id === id)?.name_en ?? "All categories";
  return (
    <>
      <PageHeader title="Department and block performance" description="Figures are computed live from grievance records in your area." />
      <div className="max-w-xs"><TextField label="Registered on or after" type="date" value={since} onChange={(e) => setSince(e.target.value)} /></div>
      <Tabs label="Performance views" active={tab} onChange={setTab} items={[
        { id: "departments", label: "Departments", content: (
          <div className="grid grid-cols-1 gap-5">
            {deps.data?.length ? <Panel title="Open and overdue by department"><Chart title="Open and overdue by department" horizontal categories={deps.data.map((d) => d.name)}
              series={[{ name: "Open", values: deps.data.map((d) => d.open) }, { name: "Overdue", values: deps.data.map((d) => d.overdue), color: "#b3261e" }]} /></Panel> : null}
            <PerfTable rows={deps.data} loading={deps.isLoading} caption="Department performance" filterKey="department_id" />
          </div>) },
        { id: "blocks", label: "Blocks", content: <PerfTable rows={blocks.data} loading={blocks.isLoading} caption="Block performance" filterKey="block_id" /> },
        { id: "escalations", label: "Escalations (30 days)", content: (
          <DataTable<Esc> caption="Escalations in the last 30 days" rows={esc.data} rowKey={(e) => `${e.grievance_id}-${e.level}`} loading={esc.isLoading} emptyTitle="No escalations"
            columns={[{ key: "r", header: "Grievance", render: (e) => <Link to={`/grievances/${e.grievance_id}`}>{e.reference_no}</Link> },
              { key: "l", header: "Level", render: (e) => e.level }, { key: "t", header: "Trigger", render: (e) => (e.trigger === "sla_breach" ? "Time limit exceeded" : "Manual") },
              { key: "why", header: "Reason", render: (e) => e.reason }, { key: "d", header: "Date", render: (e) => formatShortIST(e.created_at) }]} />) },
        { id: "sla", label: "Time limits (SLA)", content: (
          <DataTable<Sla> caption="Configured resolution time limits" rows={sla.data} rowKey={(s) => s.id} loading={sla.isLoading}
            emptyTitle="No time limits are configured" emptyMessage="Without a configured policy, grievances have no due date. Policies are set under Configuration."
            columns={[{ key: "n", header: "Policy", render: (s) => s.name }, { key: "c", header: "Category", render: (s) => catName(s.category_id) },
              { key: "p", header: "Priority", render: (s) => (s.priority ? titleCase(s.priority) : "Any") }, { key: "h", header: "Hours", align: "right", render: (s) => s.resolution_hours },
              { key: "ref", header: "Authority", render: (s) => s.legal_reference ?? "-" }, { key: "a", header: "Active", render: (s) => (s.is_active ? "Yes" : "No") }]} />) },
      ]} />
    </>
  );
}
