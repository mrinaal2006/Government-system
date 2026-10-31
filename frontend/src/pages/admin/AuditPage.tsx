import { useState } from "react";

import { Alert, Button, DataTable, PageHeader, Pagination, SelectField, TextField } from "@/design-system";
import { getJson, errorMessage } from "@/lib/api/client";
import { formatShortIST } from "@/lib/format";
import { useApi } from "@/lib/hooks";

interface Entry { seq: number; occurred_at: string; actor_username: string | null; action: string; resource_type: string | null; resource_id: string | null; outcome: string; ip_address: string | null; request_id: string | null; details: Record<string, unknown> }

export function AuditPage() {
  const [f, setF] = useState({ action: "", actor: "", outcome: "" });
  const [offset, setOffset] = useState(0);
  const logs = useApi<{ items: Entry[]; total: number }>("/audit/logs", { ...f, limit: 50, offset });
  const [verify, setVerify] = useState<{ valid: boolean; checked: number; first_invalid_seq: number | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  return (
    <>
      <PageHeader title="Audit log" description="Append-only record of security and administrative actions, protected by a hash chain."
        actions={<Button variant="secondary" onClick={() => getJson<typeof verify>("/audit/verify").then(setVerify, (e) => setErr(errorMessage(e)))}>Verify integrity</Button>} />
      {verify ? <Alert tone={verify.valid ? "success" : "danger"} live className="mb-4"
        title={verify.valid ? `Integrity verified: ${verify.checked} entries, chain intact.` : `Integrity check FAILED at entry ${verify.first_invalid_seq}. Report to the security officer.`} /> : null}
      {err ? <Alert tone="danger" title={err} className="mb-4" /> : null}
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
        <TextField label="Action starts with" hint="For example grievance. or auth.login" value={f.action} onChange={(e) => { setF({ ...f, action: e.target.value }); setOffset(0); }} />
        <TextField label="Username" value={f.actor} onChange={(e) => { setF({ ...f, actor: e.target.value }); setOffset(0); }} />
        <SelectField label="Outcome" placeholder="Any" options={["success", "failure", "denied", "warning"].map((o) => ({ value: o, label: o }))} value={f.outcome} onChange={(e) => { setF({ ...f, outcome: e.target.value }); setOffset(0); }} />
      </div>
      <DataTable<Entry> caption="Audit entries" rows={logs.data?.items} rowKey={(e) => String(e.seq)} loading={logs.isLoading}
        error={logs.isError ? { message: errorMessage(logs.error) } : null}
        columns={[
          { key: "t", header: "Time (IST)", render: (e) => formatShortIST(e.occurred_at) },
          { key: "u", header: "User", render: (e) => e.actor_username ?? "system" },
          { key: "a", header: "Action", render: (e) => <code>{e.action}</code> },
          { key: "o", header: "Outcome", render: (e) => e.outcome },
          { key: "r", header: "Resource", render: (e) => (e.resource_type ? `${e.resource_type} ${e.resource_id?.slice(0, 8) ?? ""}` : "-") },
          { key: "ip", header: "IP", render: (e) => e.ip_address ?? "-" },
          { key: "d", header: "Details", render: (e) => <code className="text-xs break-all">{JSON.stringify(e.details)}</code> },
        ]} />
      {logs.data ? <Pagination total={logs.data.total} limit={50} offset={offset} onChange={setOffset} label="entries" /> : null}
    </>
  );
}
