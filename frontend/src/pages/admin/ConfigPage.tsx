import { useState, type FormEvent, type ReactNode } from "react";

import { Alert, Button, Checkbox, DataTable, PageHeader, Panel, SelectField, StatusBadge, Tabs, TextAreaField, TextField } from "@/design-system";
import { apiSend, errorMessage } from "@/lib/api/client";
import { formatShortIST, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { options, useCategories, useDepartments, useSources, useUnits, type Category, type Department, type Source, type Unit } from "@/lib/reference";
import { useQueryClient } from "@tanstack/react-query";

type Msg = { tone: "success" | "danger"; text: string } | null;

function useSaver(setMsg: (m: Msg) => void, prefixes: string[]) {
  const qc = useQueryClient();
  return async (fn: () => Promise<unknown>, text: string) => {
    try {
      await fn();
      setMsg({ tone: "success", text });
      await qc.invalidateQueries({ predicate: (q) => prefixes.some((p) => String(q.queryKey[0] ?? "").startsWith(p)) });
      return true;
    } catch (e) {
      setMsg({ tone: "danger", text: errorMessage(e) });
      return false;
    }
  };
}

function Form({ title, onSubmit, children }: { title: string; onSubmit: () => Promise<boolean>; children: ReactNode }) {
  return (
    <Panel title={title}>
      <form noValidate onSubmit={(e: FormEvent) => { e.preventDefault(); void onSubmit(); }}>
        {children}
        <Button type="submit">Save</Button>
      </form>
    </Panel>
  );
}

export function ConfigPage() {
  const [tab, setTab] = useState("departments");
  const [msg, setMsg] = useState<Msg>(null);
  return (
    <>
      <PageHeader title="Configuration" description="Master data and settings. Changes take effect immediately and are recorded in the audit log." />
      {msg ? <Alert tone={msg.tone} title={msg.text} live className="mb-4" /> : null}
      <Tabs label="Configuration sections" active={tab} onChange={(t) => { setTab(t); setMsg(null); }} items={[
        { id: "departments", label: "Departments", content: <Departments setMsg={setMsg} /> },
        { id: "categories", label: "Issue categories", content: <Categories setMsg={setMsg} /> },
        { id: "sources", label: "Grievance sources", content: <Sources setMsg={setMsg} /> },
        { id: "geography", label: "Geography", content: <Geography setMsg={setMsg} /> },
        { id: "boundaries", label: "Boundary data", content: <Boundaries setMsg={setMsg} /> },
        { id: "sla", label: "Time limits (SLA)", content: <SlaPolicies setMsg={setMsg} /> },
        { id: "rules", label: "Classification rules", content: <Rules setMsg={setMsg} /> },
        { id: "risk", label: "Risk model", content: <RiskModel setMsg={setMsg} /> },
      ]} />
    </>
  );
}

const CODE_HINT = "Upper case letters, digits and underscores, starting with a letter (for example WATER_SUPPLY).";

function Departments({ setMsg }: { setMsg: (m: Msg) => void }) {
  const deps = useDepartments();
  const save = useSaver(setMsg, ["/reference/departments"]);
  const [f, setF] = useState({ code: "", name_en: "", name_local: "", parent_id: "" });
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[2fr_1fr]">
      <DataTable<Department> caption="Departments" rows={deps.data} rowKey={(d) => d.id} loading={deps.isLoading} emptyTitle="No departments yet"
        columns={[{ key: "c", header: "Code", render: (d) => <code>{d.code}</code> }, { key: "n", header: "Name", render: (d) => d.name_en },
          { key: "l", header: "Local name", render: (d) => d.name_local ?? "-" },
          { key: "a", header: "Status", render: (d) => <Button size="sm" variant="quiet" onClick={() => void save(() => apiSend("PATCH", `/admin/departments/${d.id}`, { code: d.code, name_en: d.name_en, is_active: !d.is_active }), "Updated.")}>{d.is_active ? "Active (deactivate)" : "Inactive (activate)"}</Button> }]} />
      <Form title="Add department" onSubmit={() => save(() => apiSend("POST", "/admin/departments", { ...f, name_local: f.name_local || null, parent_id: f.parent_id || null }), "Department added.").then((ok) => { if (ok) setF({ code: "", name_en: "", name_local: "", parent_id: "" }); return ok; })}>
        <TextField label="Code" required hint={CODE_HINT} value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
        <TextField label="Name (English)" required value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} />
        <TextField label="Name (local language)" lang="hi" value={f.name_local} onChange={(e) => setF({ ...f, name_local: e.target.value })} />
        <SelectField label="Parent department" options={options(deps.data)} placeholder="None" value={f.parent_id} onChange={(e) => setF({ ...f, parent_id: e.target.value })} />
      </Form>
    </div>
  );
}

function Categories({ setMsg }: { setMsg: (m: Msg) => void }) {
  const cats = useCategories();
  const deps = useDepartments();
  const save = useSaver(setMsg, ["/reference/categories"]);
  const blank = { code: "", name_en: "", parent_id: "", default_department_id: "", is_essential_service: false };
  const [f, setF] = useState(blank);
  const name = (id: string | null) => (id ? cats.data?.find((c) => c.id === id)?.name_en ?? deps.data?.find((d) => d.id === id)?.name_en : null) ?? "-";
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[2fr_1fr]">
      <DataTable<Category> caption="Issue categories" rows={cats.data} rowKey={(c) => c.id} loading={cats.isLoading} emptyTitle="No categories yet"
        columns={[{ key: "c", header: "Code", render: (c) => <code>{c.code}</code> }, { key: "n", header: "Name", render: (c) => c.name_en },
          { key: "p", header: "Parent", render: (c) => name(c.parent_id) }, { key: "d", header: "Default department", render: (c) => name(c.default_department_id) },
          { key: "e", header: "Essential service", render: (c) => (c.is_essential_service ? "Yes" : "No") }]} />
      <Form title="Add category or subcategory" onSubmit={() => save(() => apiSend("POST", "/admin/categories", { ...f, parent_id: f.parent_id || null, default_department_id: f.default_department_id || null }), "Category added.").then((ok) => { if (ok) setF(blank); return ok; })}>
        <TextField label="Code" required hint={CODE_HINT} value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.toUpperCase() })} />
        <TextField label="Name" required value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} />
        <SelectField label="Parent category (for a subcategory)" options={options(cats.data?.filter((c) => !c.parent_id))} placeholder="None (top level)" value={f.parent_id} onChange={(e) => setF({ ...f, parent_id: e.target.value })} />
        <SelectField label="Default department" options={options(deps.data)} placeholder="None" value={f.default_department_id} onChange={(e) => setF({ ...f, default_department_id: e.target.value })} />
        <Checkbox label="Essential service" hint="Used by the early-warning indicator for service disruption." checked={f.is_essential_service} onChange={(e) => setF({ ...f, is_essential_service: e.target.checked })} />
      </Form>
    </div>
  );
}

function Sources({ setMsg }: { setMsg: (m: Msg) => void }) {
  const sources = useSources();
  const save = useSaver(setMsg, ["/reference/sources"]);
  return (
    <>
      <Alert tone="info" title="Set a source to 'live API' only after an authorised, documented integration exists." className="mb-4" />
      <DataTable<Source> caption="Grievance sources" rows={sources.data} rowKey={(s) => s.id} loading={sources.isLoading}
        columns={[{ key: "c", header: "Code", render: (s) => <code>{s.code}</code> }, { key: "n", header: "Name", render: (s) => s.name_en },
          { key: "t", header: "Channel", render: (s) => titleCase(s.channel_type) },
          { key: "m", header: "Integration", render: (s) => (
            <SelectField label={`Integration mode for ${s.name_en}`} options={["not_configured", "file_import", "development_adapter", "live_api"].map((m) => ({ value: m, label: titleCase(m) }))} placeholder="Select"
              value={s.integration_mode} onChange={(e) => e.target.value && void save(() => apiSend("PATCH", `/admin/sources/${s.id}`, { integration_mode: e.target.value }), "Integration mode updated.")} />) }]} />
    </>
  );
}

const LEVELS = [
  { value: "districts", label: "Districts", parent: null },
  { value: "subdivisions", label: "Subdivisions", parent: "districts" },
  { value: "blocks", label: "Blocks", parent: "districts" },
  { value: "gram_panchayats", label: "Gram panchayats", parent: "blocks" },
  { value: "villages", label: "Villages", parent: "gram_panchayats" },
  { value: "municipalities", label: "Municipalities", parent: "districts" },
  { value: "wards", label: "Wards", parent: "municipalities" },
];
const PARENT_FIELD: Record<string, string> = { districts: "district_id", blocks: "block_id", gram_panchayats: "gram_panchayat_id", municipalities: "municipality_id" };

function Geography({ setMsg }: { setMsg: (m: Msg) => void }) {
  const [level, setLevel] = useState("districts");
  const meta = LEVELS.find((l) => l.value === level)!;
  const units = useUnits(level);
  const parents = useUnits(meta.parent ?? "districts", null, Boolean(meta.parent));
  const save = useSaver(setMsg, ["/reference/units"]);
  const blank = { name_en: "", name_local: "", lgd_code: "", parent: "", state_name_en: "", body_type: "municipal_council", ward_number: "" };
  const [f, setF] = useState(blank);
  const submit = () => {
    const body: Record<string, unknown> = { name_en: level === "wards" ? `Ward ${f.ward_number}` : f.name_en, name_local: f.name_local || null, lgd_code: f.lgd_code || null };
    if (meta.parent) body[PARENT_FIELD[meta.parent]!] = f.parent;
    if (level === "districts") body.state_name_en = f.state_name_en;
    if (level === "municipalities") body.body_type = f.body_type;
    if (level === "wards") body.ward_number = f.ward_number;
    return save(() => apiSend("POST", `/admin/units/${level}`, body), "Unit added.").then((ok) => { if (ok) setF(blank); return ok; });
  };
  return (
    <>
      <Alert tone="info" title="Enter administrative units only from verified sources such as the Local Government Directory (LGD)." className="mb-4" />
      <div className="max-w-xs"><SelectField label="Level" options={LEVELS} placeholder="Districts" value={level} onChange={(e) => { setLevel(e.target.value || "districts"); setF(blank); }} /></div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[2fr_1fr]">
        <DataTable<Unit> caption={meta.label} rows={units.data} rowKey={(u) => u.id} loading={units.isLoading} emptyTitle={`No ${meta.label.toLowerCase()} yet`}
          columns={[{ key: "n", header: "Name", render: (u) => u.name_en }, { key: "c", header: "LGD code", render: (u) => u.lgd_code ?? "-" },
            { key: "g", header: "Boundary", render: (u) => (u.has_geometry ? <StatusBadge tone="success">Present</StatusBadge> : <StatusBadge>None</StatusBadge>) }]} />
        <Form title={`Add to ${meta.label.toLowerCase()}`} onSubmit={submit}>
          {meta.parent ? <SelectField label={`Parent (${titleCase(meta.parent)})`} required options={options(parents.data)} value={f.parent} onChange={(e) => setF({ ...f, parent: e.target.value })} /> : null}
          {level === "wards" ? <TextField label="Ward number" required value={f.ward_number} onChange={(e) => setF({ ...f, ward_number: e.target.value })} />
            : <TextField label="Name (English)" required value={f.name_en} onChange={(e) => setF({ ...f, name_en: e.target.value })} />}
          <TextField label="Name (local language)" lang="hi" value={f.name_local} onChange={(e) => setF({ ...f, name_local: e.target.value })} />
          <TextField label="LGD code" inputMode="numeric" value={f.lgd_code} onChange={(e) => setF({ ...f, lgd_code: e.target.value })} />
          {level === "districts" ? <TextField label="State" required value={f.state_name_en} onChange={(e) => setF({ ...f, state_name_en: e.target.value })} /> : null}
          {level === "municipalities" ? <SelectField label="Body type" options={["municipal_corporation", "municipal_council", "nagar_panchayat", "cantonment_board", "other"].map((b) => ({ value: b, label: titleCase(b) }))}
            value={f.body_type} onChange={(e) => setF({ ...f, body_type: e.target.value })} /> : null}
        </Form>
      </div>
    </>
  );
}

function Boundaries({ setMsg }: { setMsg: (m: Msg) => void }) {
  const datasets = useApi<Array<{ id: string; name: string; publisher: string; dataset_version: string; source_reference: string; acquired_on: string; checksum_sha256: string | null }>>("/admin/boundary-datasets");
  const save = useSaver(setMsg, ["/admin/boundary-datasets", "/reference/units", "/gis"]);
  const [d, setD] = useState({ name: "", publisher: "", dataset_version: "", source_reference: "", licence: "", acquired_on: "" });
  const [imp, setImp] = useState({ dataset_id: "", level: "blocks", match_property: "lgd_code" });
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<{ matched: number; unmatched: string[]; invalid: string[] } | null>(null);
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Form title="1. Register a verified dataset" onSubmit={() => save(() => apiSend("POST", "/admin/boundary-datasets", { ...d, licence: d.licence || null }), "Dataset registered.")}>
        <TextField label="Dataset name" required value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} />
        <TextField label="Publisher" required hint="For example the state GIS cell or Survey of India" value={d.publisher} onChange={(e) => setD({ ...d, publisher: e.target.value })} />
        <TextField label="Version" required value={d.dataset_version} onChange={(e) => setD({ ...d, dataset_version: e.target.value })} />
        <TextField label="Source reference" required hint="URL, order number or letter reference" value={d.source_reference} onChange={(e) => setD({ ...d, source_reference: e.target.value })} />
        <TextField label="Licence" value={d.licence} onChange={(e) => setD({ ...d, licence: e.target.value })} />
        <TextField label="Date acquired" type="date" required value={d.acquired_on} onChange={(e) => setD({ ...d, acquired_on: e.target.value })} />
      </Form>
      <Panel title="2. Import GeoJSON boundaries">
        <form noValidate onSubmit={async (e) => {
          e.preventDefault();
          if (!file || !imp.dataset_id) { setMsg({ tone: "danger", text: "Choose a dataset and a GeoJSON file." }); return; }
          const fd = new FormData();
          Object.entries(imp).forEach(([k, v]) => fd.append(k, v));
          fd.append("file", file);
          await save(async () => setResult(await apiSend("POST", "/admin/boundaries/import", fd)), "Import finished.");
        }}>
          <SelectField label="Dataset" required options={(datasets.data ?? []).map((x) => ({ value: x.id, label: `${x.name} v${x.dataset_version}` }))} value={imp.dataset_id} onChange={(e) => setImp({ ...imp, dataset_id: e.target.value })} />
          <SelectField label="Level" options={LEVELS.filter((l) => l.value !== "wards")} value={imp.level} onChange={(e) => setImp({ ...imp, level: e.target.value })} />
          <TextField label="Feature property holding the LGD code" value={imp.match_property} onChange={(e) => setImp({ ...imp, match_property: e.target.value })} />
          <label htmlFor="geojson" className="block font-semibold">GeoJSON file (EPSG:4326)</label>
          <input id="geojson" type="file" accept=".geojson,.json,application/geo+json,application/json" className="my-2 block" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <Button type="submit">Import</Button>
        </form>
        {result ? <Alert tone={result.invalid.length || result.unmatched.length ? "warning" : "success"} title={`${result.matched} boundaries attached`} className="mt-3">
          {result.unmatched.length ? <p className="m-0">Not matched (not created): {result.unmatched.slice(0, 20).join(", ")}</p> : null}
          {result.invalid.length ? <p className="m-0">Rejected as invalid geometry: {result.invalid.slice(0, 20).join(", ")}</p> : null}
        </Alert> : null}
      </Panel>
      <div className="xl:col-span-2">
        <DataTable caption="Registered datasets" rows={datasets.data} rowKey={(x) => x.id} loading={datasets.isLoading} emptyTitle="No datasets registered"
          columns={[{ key: "n", header: "Dataset", render: (x) => x.name }, { key: "p", header: "Publisher", render: (x) => x.publisher }, { key: "v", header: "Version", render: (x) => x.dataset_version },
            { key: "s", header: "Source", render: (x) => x.source_reference }, { key: "a", header: "Acquired", render: (x) => x.acquired_on }, { key: "h", header: "SHA-256", render: (x) => <code className="text-xs">{x.checksum_sha256?.slice(0, 16) ?? "-"}</code> }]} />
      </div>
    </div>
  );
}

function SlaPolicies({ setMsg }: { setMsg: (m: Msg) => void }) {
  const list = useApi<Array<{ id: string; name: string; category_id: string | null; priority: string | null; resolution_hours: number; legal_reference: string | null; is_active: boolean }>>("/admin/sla-policies");
  const cats = useCategories();
  const save = useSaver(setMsg, ["/admin/sla-policies"]);
  const [f, setF] = useState({ name: "", category_id: "", priority: "", resolution_hours: "", legal_reference: "" });
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[2fr_1fr]">
      <DataTable caption="Time limit policies" rows={list.data} rowKey={(p) => p.id} loading={list.isLoading} emptyTitle="No policies. Grievances will have no due date."
        columns={[{ key: "n", header: "Policy", render: (p) => p.name }, { key: "c", header: "Category", render: (p) => cats.data?.find((c) => c.id === p.category_id)?.name_en ?? "Any" },
          { key: "p", header: "Priority", render: (p) => (p.priority ? titleCase(p.priority) : "Any") }, { key: "h", header: "Hours", align: "right", render: (p) => p.resolution_hours },
          { key: "r", header: "Authority", render: (p) => p.legal_reference ?? "-" }]} />
      <Form title="Add policy" onSubmit={() => save(() => apiSend("POST", "/admin/sla-policies", { name: f.name, category_id: f.category_id || null, priority: f.priority || null,
        resolution_hours: Number(f.resolution_hours), legal_reference: f.legal_reference || null }), "Policy added.")}>
        <Alert tone="info" title="Use only timelines established by an official order or notification, and cite it." className="mb-3" />
        <TextField label="Policy name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <SelectField label="Category" options={options(cats.data?.filter((c) => !c.parent_id))} placeholder="Any category" value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })} />
        <SelectField label="Priority" options={["low", "normal", "high", "urgent"].map((p) => ({ value: p, label: titleCase(p) }))} placeholder="Any priority" value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })} />
        <TextField label="Resolution time (hours)" type="number" min={1} required value={f.resolution_hours} onChange={(e) => setF({ ...f, resolution_hours: e.target.value })} />
        <TextField label="Order / notification reference" value={f.legal_reference} onChange={(e) => setF({ ...f, legal_reference: e.target.value })} />
      </Form>
    </div>
  );
}

function Rules({ setMsg }: { setMsg: (m: Msg) => void }) {
  const rules = useApi<Array<{ id: string; category_id: string; keyword: string; weight: number; is_active: boolean }>>("/admin/classification-rules");
  const cats = useCategories();
  const save = useSaver(setMsg, ["/admin/classification-rules"]);
  const [f, setF] = useState({ category_id: "", keyword: "", weight: "1" });
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[2fr_1fr]">
      <DataTable caption="Keyword classification rules" rows={rules.data} rowKey={(r) => r.id} loading={rules.isLoading} emptyTitle="No rules: the classifier makes no suggestions"
        columns={[{ key: "k", header: "Keyword", render: (r) => r.keyword }, { key: "c", header: "Suggests category", render: (r) => cats.data?.find((c) => c.id === r.category_id)?.name_en ?? "-" },
          { key: "w", header: "Weight", align: "right", render: (r) => r.weight }, { key: "a", header: "Active", render: (r) => (r.is_active ? "Yes" : "No") }]} />
      <Form title="Add rule" onSubmit={() => save(() => apiSend("POST", "/admin/classification-rules", { category_id: f.category_id, keyword: f.keyword, weight: Number(f.weight) }), "Rule added.").then((ok) => { if (ok) setF({ ...f, keyword: "" }); return ok; })}>
        <p className="mt-0 text-sm text-ink-muted">When a complaint contains the keyword, the category is suggested to officers with the keyword shown as evidence.</p>
        <SelectField label="Category" required options={options(cats.data)} value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })} />
        <TextField label="Keyword or phrase" required value={f.keyword} onChange={(e) => setF({ ...f, keyword: e.target.value })} />
        <TextField label="Weight (0.1 to 10)" type="number" step="0.1" min={0.1} max={10} value={f.weight} onChange={(e) => setF({ ...f, weight: e.target.value })} />
      </Form>
    </div>
  );
}

function RiskModel({ setMsg }: { setMsg: (m: Msg) => void }) {
  const models = useApi<Array<{ id: string; version: number; parameters: Record<string, unknown>; is_active: boolean; is_provisional: boolean; notes: string | null; created_at: string }>>("/admin/risk-models");
  const save = useSaver(setMsg, ["/admin/risk-models"]);
  const active = models.data?.find((m) => m.is_active);
  const [json, setJson] = useState("");
  const [notes, setNotes] = useState("");
  const [approved, setApproved] = useState(false);
  return (
    <div className="grid grid-cols-1 gap-5">
      {active?.is_provisional ? <Alert tone="warning" title={`Active risk model version ${active.version} is PROVISIONAL`}>Its weights and thresholds are starting values that require review and approval by the District Magistrate.</Alert> : null}
      <Panel title="Create a new version" description="The new version becomes active immediately; earlier versions are kept for traceability.">
        <form noValidate onSubmit={(e) => {
          e.preventDefault();
          let parameters: unknown;
          try { parameters = JSON.parse(json || JSON.stringify(active?.parameters ?? {})); } catch { setMsg({ tone: "danger", text: "The parameters are not valid JSON." }); return; }
          void save(() => apiSend("POST", "/admin/risk-models", { parameters, notes, approved }), "New risk model version activated.");
        }}>
          <TextAreaField label="Parameters (JSON)" className="min-h-72 font-mono text-sm" value={json || JSON.stringify(active?.parameters ?? {}, null, 2)} onChange={(e) => setJson(e.target.value)} />
          <TextField label="Change note" required hint="Why the change is being made and on whose authority" value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Checkbox label="Approved by the competent authority" checked={approved} onChange={(e) => setApproved(e.target.checked)} />
          <Button type="submit">Activate new version</Button>
        </form>
      </Panel>
      <DataTable caption="Risk model versions" rows={models.data} rowKey={(m) => m.id} loading={models.isLoading}
        columns={[{ key: "v", header: "Version", render: (m) => m.version }, { key: "a", header: "Active", render: (m) => (m.is_active ? "Yes" : "No") },
          { key: "p", header: "Approval", render: (m) => (m.is_provisional ? <StatusBadge tone="warning">Provisional</StatusBadge> : <StatusBadge tone="success">Approved</StatusBadge>) },
          { key: "n", header: "Note", render: (m) => m.notes ?? "-" }, { key: "c", header: "Created", render: (m) => formatShortIST(m.created_at) }]} />
    </div>
  );
}
