import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Button, Checkbox, DataTable, PageHeader, Pagination, Panel, SelectField, StatusBadge, TextField, type SortDirection } from "@/design-system";
import { errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { formatShortIST, RISK_TONE, STATUS_LABELS, STATUS_TONE, titleCase } from "@/lib/format";
import { useApi, useUrlFilters } from "@/lib/hooks";
import { options, useCategories, useDepartments, useSources, useUnits } from "@/lib/reference";

export interface GrievanceRow {
  id: string; reference_no: string; subject: string; status: string; priority: string; category: string | null;
  department: string | null; block: string | null; village: string | null; assigned_officer: string | null;
  source: string | null; registered_at: string; due_at: string | null; overdue: boolean; risk_level: string | null;
  escalation_level: number; reopened_count: number;
}

type Filters = {
  q?: string; status: string[]; priority: string[]; category_id?: string; department_id?: string; block_id?: string;
  village_id?: string; source_id?: string; overdue?: string; open_only?: string; escalated?: string; risk_level: string[];
  assigned_to_me?: string; registered_from?: string; registered_to?: string; sort?: string; order?: string; offset?: string;
};
const KEYS: (keyof Filters)[] = ["q", "status", "priority", "category_id", "department_id", "block_id", "village_id", "source_id",
  "overdue", "open_only", "escalated", "risk_level", "assigned_to_me", "registered_from", "registered_to", "sort", "order", "offset"];
const MULTI: (keyof Filters)[] = ["status", "priority", "risk_level"];
const LIMIT = 25;

export function GrievanceListPage() {
  const { can } = useAuth();
  const [f, setF] = useUrlFilters<Filters>(KEYS, MULTI);
  const [q, setQ] = useState(f.q ?? "");
  const cats = useCategories();
  const deps = useDepartments();
  const sources = useSources();
  const blocks = useUnits("blocks");
  const offset = Number(f.offset ?? 0);
  const list = useApi<{ items: GrievanceRow[]; total: number }>("/grievances", { ...f, offset, limit: LIMIT });
  const set = (patch: Partial<Filters>) => setF({ ...patch, offset: undefined });
  const activeCount = KEYS.filter((k) => !["sort", "order", "offset"].includes(k) && (Array.isArray(f[k]) ? (f[k] as string[]).length : f[k])).length;

  return (
    <>
      <PageHeader title="Grievance register" description="All grievances within your authorised area."
        actions={can("grievance.create") ? <Link to="/grievances/new" className="rounded-sm border border-brand bg-brand px-4 py-2 font-semibold text-on-brand no-underline">Register grievance</Link> : null} />
      <Panel title="Search and filter" description={activeCount ? `${activeCount} filter(s) applied` : undefined}
        actions={activeCount ? <Button size="sm" variant="secondary" onClick={() => { setQ(""); setF({ status: [], priority: [], risk_level: [] } as Partial<Filters>); }}>Clear all</Button> : null}>
        <form role="search" onSubmit={(e: FormEvent) => { e.preventDefault(); set({ q }); }} className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <TextField label="Search reference, subject or description" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <Button type="submit" className="mb-4">Search</Button>
        </form>
        <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3 xl:grid-cols-4">
          <SelectField label="Status" options={Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }))} placeholder="Any status"
            value={f.status[0] ?? ""} onChange={(e) => set({ status: e.target.value ? [e.target.value] : [] })} />
          <SelectField label="Priority" options={["urgent", "high", "normal", "low"].map((p) => ({ value: p, label: titleCase(p) }))} placeholder="Any priority"
            value={f.priority[0] ?? ""} onChange={(e) => set({ priority: e.target.value ? [e.target.value] : [] })} />
          <SelectField label="Category" options={options(cats.data?.filter((c) => !c.parent_id))} placeholder="Any category"
            value={f.category_id ?? ""} onChange={(e) => set({ category_id: e.target.value || undefined })} />
          <SelectField label="Department" options={options(deps.data)} placeholder="Any department"
            value={f.department_id ?? ""} onChange={(e) => set({ department_id: e.target.value || undefined })} />
          <SelectField label="Block" options={options(blocks.data)} placeholder="Any block"
            value={f.block_id ?? ""} onChange={(e) => set({ block_id: e.target.value || undefined, village_id: undefined })} />
          <SelectField label="Source" options={options(sources.data)} placeholder="Any source"
            value={f.source_id ?? ""} onChange={(e) => set({ source_id: e.target.value || undefined })} />
          <SelectField label="Risk level" options={["critical", "high", "watch", "normal"].map((p) => ({ value: p, label: titleCase(p) }))} placeholder="Any risk"
            value={f.risk_level[0] ?? ""} onChange={(e) => set({ risk_level: e.target.value ? [e.target.value] : [] })} />
          <TextField label="Registered from (date)" type="date" value={f.registered_from?.slice(0, 10) ?? ""}
            onChange={(e) => set({ registered_from: e.target.value || undefined })} />
        </div>
        <div className="flex flex-wrap gap-x-6">
          <Checkbox label="Open only" checked={f.open_only === "true"} onChange={(e) => set({ open_only: e.target.checked ? "true" : undefined })} />
          <Checkbox label="Overdue only" checked={f.overdue === "true"} onChange={(e) => set({ overdue: e.target.checked ? "true" : undefined })} />
          <Checkbox label="Escalated only" checked={f.escalated === "true"} onChange={(e) => set({ escalated: e.target.checked ? "true" : undefined })} />
          <Checkbox label="Assigned to me" checked={f.assigned_to_me === "true"} onChange={(e) => set({ assigned_to_me: e.target.checked ? "true" : undefined })} />
        </div>
      </Panel>
      <div className="mt-5">
        <DataTable<GrievanceRow>
          caption="Grievances" rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading}
          error={list.isError ? { message: errorMessage(list.error), onRetry: () => void list.refetch() } : null}
          emptyTitle="No grievances match these filters"
          sort={{ key: f.sort ?? "registered_at", direction: (f.order === "asc" ? "ascending" : "descending") as SortDirection }}
          onSortChange={(key, dir) => setF({ sort: key, order: dir === "ascending" ? "asc" : "desc" })}
          columns={[
            { key: "reference_no", header: "Reference", sortable: true, render: (r) => <Link to={`/grievances/${r.id}`} className="font-semibold whitespace-nowrap">{r.reference_no}</Link> },
            { key: "subject", header: "Subject", render: (r) => r.subject },
            { key: "status", header: "Status", sortable: true, render: (r) => <StatusBadge tone={STATUS_TONE[r.status]}>{STATUS_LABELS[r.status] ?? r.status}</StatusBadge> },
            { key: "priority", header: "Priority", sortable: true, render: (r) => titleCase(r.priority) },
            { key: "category", header: "Category / department", render: (r) => <>{r.category ?? "Unclassified"}<br /><span className="text-ink-muted">{r.department ?? "-"}</span></> },
            { key: "location", header: "Location", render: (r) => [r.village, r.block].filter(Boolean).join(", ") || "-" },
            { key: "officer", header: "Assigned to", render: (r) => r.assigned_officer ?? "Not assigned" },
            { key: "registered_at", header: "Registered (IST)", sortable: true, render: (r) => formatShortIST(r.registered_at) },
            { key: "due_at", header: "Due", sortable: true, render: (r) => r.overdue ? <StatusBadge tone="danger">{`Overdue: ${formatShortIST(r.due_at)}`}</StatusBadge> : formatShortIST(r.due_at) },
            { key: "risk", header: "Risk", render: (r) => r.risk_level ? <StatusBadge tone={RISK_TONE[r.risk_level]}>{titleCase(r.risk_level)}</StatusBadge> : "-" },
          ]}
        />
        {list.data ? <Pagination total={list.data.total} limit={LIMIT} offset={offset} label="grievances" onChange={(o) => setF({ offset: String(o) })} /> : null}
      </div>
    </>
  );
}
