import { useState } from "react";

import { Alert, Button, DataTable, PageHeader, Panel, SelectField, StatusBadge } from "@/design-system";
import { apiSend, errorMessage } from "@/lib/api/client";
import { formatShortIST, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";

interface Batch { id: string; source_code: string; adapter: string; filename: string; status: string; total_rows: number; created_count: number; duplicate_count: number; failed_count: number; errors: Array<{ row: number | null; error?: string; warnings?: string[] }>; created_at: string }
interface Adapters { file_import: { required_columns: string[]; optional_columns: string[]; formats: string[]; max_rows: number }; development_adapter_available: boolean; sources: Array<{ code: string; name: string; integration_mode: string }> }

export function IntakePage() {
  const adapters = useApi<Adapters>("/intake/adapters");
  const batches = useApi<{ items: Batch[] }>("/intake/imports", { limit: 50 }, { refetchInterval: 5000 });
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Batch | null>(null);
  return (
    <>
      <PageHeader title="Import from grievance sources" description="Upload authorised exports from source systems. Every record keeps its source and external reference; repeated records are skipped." />
      <Alert tone="info" title="No live government integration is configured" className="mb-4">
        Live connections to the CM Helpline or other portals require a documented, authorised integration. Until then, use authorised file exports.
      </Alert>
      {msg ? <Alert tone={msg.tone} title={msg.text} live className="mb-4" /> : null}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel title="Upload a file">
          <form noValidate onSubmit={async (e) => {
            e.preventDefault();
            if (!source || !file) { setMsg({ tone: "danger", text: "Choose the source and a file." }); return; }
            setBusy(true);
            const fd = new FormData();
            fd.append("source_code", source);
            fd.append("file", file);
            try { await apiSend("POST", "/intake/imports", fd); setMsg({ tone: "success", text: "File received. Processing has started." }); void batches.refetch(); }
            catch (ex) { setMsg({ tone: "danger", text: errorMessage(ex) }); } finally { setBusy(false); }
          }}>
            <SelectField label="Source channel" required options={(adapters.data?.sources ?? []).map((s) => ({ value: s.code, label: s.name }))} value={source} onChange={(e) => setSource(e.target.value)} />
            <label htmlFor="import-file" className="block font-semibold">File (CSV in UTF-8, or XLSX)</label>
            <input id="import-file" type="file" accept=".csv,.xlsx" className="my-2 block" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            <Button type="submit" busy={busy}>Upload and import</Button>
          </form>
          {adapters.data?.development_adapter_available ? (
            <div className="mt-4 border-t border-line pt-3">
              <p className="m-0 mb-2 text-sm"><strong>Development environment:</strong> generate clearly labelled synthetic records to test the pipeline.</p>
              <Button variant="secondary" size="sm" disabled={!source} onClick={() => apiSend("POST", "/intake/development-adapter/run", { source_code: source, count: 5 })
                .then(() => { setMsg({ tone: "success", text: "Synthetic development records created." }); void batches.refetch(); }, (ex) => setMsg({ tone: "danger", text: errorMessage(ex) }))}>
                Run development adapter
              </Button>
            </div>
          ) : null}
        </Panel>
        <Panel title="File format">
          <p className="mt-0">Required columns: <code>{adapters.data?.file_import.required_columns.join(", ")}</code></p>
          <p>Optional columns: <code>{adapters.data?.file_import.optional_columns.join(", ")}</code></p>
          <p className="mb-0 text-sm text-ink-muted">Locations and categories are matched to official codes and names; anything not matched is left blank and reported, never guessed.</p>
        </Panel>
      </div>
      <h2 className="mt-6 text-lg font-semibold">Import history</h2>
      <DataTable<Batch> caption="Import history" rows={batches.data?.items} rowKey={(b) => b.id} loading={batches.isLoading} emptyTitle="No imports yet"
        columns={[
          { key: "f", header: "File", render: (b) => b.filename },
          { key: "s", header: "Source", render: (b) => titleCase(b.source_code) },
          { key: "st", header: "Status", render: (b) => <StatusBadge tone={b.status === "completed" ? "success" : b.status === "failed" ? "danger" : "info"}>{titleCase(b.status)}</StatusBadge> },
          { key: "n", header: "Rows / created / duplicates / failed", render: (b) => `${b.total_rows} / ${b.created_count} / ${b.duplicate_count} / ${b.failed_count}` },
          { key: "d", header: "Uploaded", render: (b) => formatShortIST(b.created_at) },
          { key: "x", header: "Details", render: (b) => (b.errors.length ? <Button size="sm" variant="quiet" onClick={() => setSelected(b)}>View {b.errors.length} note(s)</Button> : "-") },
        ]} />
      {selected ? (
        <Panel title={`Notes for ${selected.filename}`} className="mt-4" actions={<Button size="sm" variant="secondary" onClick={() => setSelected(null)}>Close</Button>}>
          <ul className="m-0 pl-5 text-sm">{selected.errors.map((e, i) => <li key={i}>Row {e.row ?? "-"}: {e.error ?? e.warnings?.join("; ")}</li>)}</ul>
        </Panel>
      ) : null}
    </>
  );
}
