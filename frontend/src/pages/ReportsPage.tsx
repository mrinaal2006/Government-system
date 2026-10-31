import { useState } from "react";

import { Alert, Button, Checkbox, DataTable, PageHeader, Panel, SelectField, StatusBadge, TextField } from "@/design-system";
import { API_BASE, apiSend, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { formatShortIST, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";

interface Job { id: string; report_type: string; format: string; status: string; created_at: string; completed_at: string | null; expires_at: string | null; row_count: number | null; filename: string | null; error: string | null }

const TYPES = [
  { value: "executive_summary", label: "Executive summary (narrative + department table)" },
  { value: "grievance_register", label: "Grievance register" },
  { value: "department_performance", label: "Department performance" },
  { value: "block_summary", label: "Block-wise summary" },
];

export function ReportsPage() {
  const { can } = useAuth();
  const jobs = useApi<Job[]>("/reports", undefined, { refetchInterval: 4000 });
  const [form, setForm] = useState({ report_type: "executive_summary", format: "pdf", since: "", until: "", open_only: false, include_pii: false });
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  return (
    <>
      <PageHeader title="Reports" description="Reports are generated in the background with your access rights and kept for 7 days. Every export is recorded in the audit log." />
      {msg ? <Alert tone={msg.tone} title={msg.text} live className="mb-4" /> : null}
      <Panel title="Generate a report">
        <form noValidate onSubmit={(e) => {
          e.preventDefault();
          apiSend("POST", "/reports", { report_type: form.report_type, format: form.format, parameters: {
            since: form.since ? new Date(form.since).toISOString() : null, until: form.until ? new Date(form.until).toISOString() : null,
            open_only: form.open_only, include_pii: form.include_pii } })
            .then(() => { setMsg({ tone: "success", text: "Report requested. It will appear below when ready." }); void jobs.refetch(); }, (ex) => setMsg({ tone: "danger", text: errorMessage(ex) }));
        }}>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            <SelectField label="Report" options={TYPES} placeholder="Select" value={form.report_type} onChange={(e) => setForm({ ...form, report_type: e.target.value || "executive_summary" })} />
            <SelectField label="Format" options={[{ value: "pdf", label: "PDF" }, { value: "xlsx", label: "Excel (XLSX)" }]} placeholder="PDF" value={form.format} onChange={(e) => setForm({ ...form, format: e.target.value || "pdf" })} />
            <TextField label="From date" type="date" value={form.since} onChange={(e) => setForm({ ...form, since: e.target.value })} />
            <TextField label="To date" type="date" value={form.until} onChange={(e) => setForm({ ...form, until: e.target.value })} />
          </div>
          <Checkbox label="Open grievances only" checked={form.open_only} onChange={(e) => setForm({ ...form, open_only: e.target.checked })} />
          {can("citizen.read") && form.report_type === "grievance_register" ? (
            <Checkbox label="Include complainant name and mobile number" hint="Only when strictly necessary. The export is marked as containing personal data and is audited."
              checked={form.include_pii} onChange={(e) => setForm({ ...form, include_pii: e.target.checked })} />
          ) : null}
          <Button type="submit">Generate report</Button>
        </form>
      </Panel>
      <h2 className="mt-6 text-lg font-semibold">My reports</h2>
      <DataTable<Job> caption="My reports" rows={jobs.data} rowKey={(j) => j.id} loading={jobs.isLoading} emptyTitle="No reports generated yet"
        columns={[
          { key: "t", header: "Report", render: (j) => titleCase(j.report_type) },
          { key: "f", header: "Format", render: (j) => j.format.toUpperCase() },
          { key: "s", header: "Status", render: (j) => <StatusBadge tone={j.status === "completed" ? "success" : j.status === "failed" ? "danger" : "info"}>{titleCase(j.status)}</StatusBadge> },
          { key: "r", header: "Rows", align: "right", render: (j) => j.row_count ?? "-" },
          { key: "c", header: "Requested", render: (j) => formatShortIST(j.created_at) },
          { key: "d", header: "Download", render: (j) => (j.status === "completed" && can("report.export") ? <a href={`${API_BASE}/reports/${j.id}/download`} download>{j.filename}</a> : j.error ?? "-") },
        ]} />
    </>
  );
}
