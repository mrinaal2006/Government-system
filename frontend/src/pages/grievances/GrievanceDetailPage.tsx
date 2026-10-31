import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router";

import {
  Alert,
  Button,
  DataTable,
  DescriptionList,
  Dialog,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  SelectField,
  StatusBadge,
  Tabs,
  TextAreaField,
  TextField,
} from "@/design-system";
import { API_BASE, apiSend, errorMessage, getJson } from "@/lib/api/client";
import { formatBytes, formatShortIST, RISK_TONE, STATUS_LABELS, STATUS_TONE, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { options, useCategories, useDepartments } from "@/lib/reference";
import { useQueryClient } from "@tanstack/react-query";

type Named = { id: string; name: string } | null;
interface Detail {
  id: string; reference_no: string; subject: string; description: string; summary: string | null; status: string; priority: string;
  received_at: string; registered_at: string; due_at: string | null; overdue: boolean; resolution_summary: string | null;
  reopened_count: number; escalation_level: number; location_text: string | null; duplicate_of_id: string | null; version: number;
  source: Named; category: Named; subcategory: Named; department: Named; district: Named; subdivision: Named; block: Named;
  gram_panchayat: Named; village: Named; municipality: Named; ward: Named; assigned_officer: Named; created_by: Named;
  complainant: { masked: boolean; name: string | null; mobile: string | null; email: string | null; address: string | null; consent_recorded: boolean } | null;
  risk: { level: string; score: number; factors: Array<{ factor: string; points: number; detail: string }>; model_version: number; assessed_at: string } | null;
  sla_events: Array<{ event_type: string; occurred_at: string; cycle: number }>;
  escalations: Array<{ level: number; trigger: string; reason: string; created_at: string }>;
  allowed_actions: string[];
}
interface History {
  status_history: Array<{ from_status: string | null; to_status: string; action: string; reason: string | null; actor: string | null; occurred_at: string }>;
  assignments: Array<{ officer: string; assigned_by: string; assigned_at: string; ended_at: string | null; reason: string | null }>;
  comments: Array<{ id: string; kind: string; body: string; author: string; created_at: string }>;
  attachments: Array<{ id: string; filename: string; content_type: string; size_bytes: number; scan_status: string; uploaded_at: string }>;
  external_references: Array<{ source_id: string; external_id: string; recorded_at: string }>;
  relationships: Array<{ related_grievance_id: string; relation_type: string; note: string | null }>;
}
interface Classification {
  id: string; task: string; model_id: string; model_version: string; prediction: Record<string, string | null>; confidence: number | null;
  processing_status: string; evidence: unknown[]; verification_status: string; verified_by: string | null; created_at: string; input_ref: string;
}
interface Intel {
  classifications: Classification[];
  duplicates: Array<{ id: string; candidate_grievance_id: string; reference_no: string; subject: string; similarity: number; evidence: unknown[]; review_status: string }>;
  notice: string;
}

const TRANSITION_LABELS: Record<string, string> = {
  start_work: "Start work",
  submit_resolution: "Submit resolution",
  accept_resolution: "Accept resolution",
  return_resolution: "Return for further action",
  close: "Close grievance",
  reopen: "Reopen",
};
const NOTE_REQUIRED = new Set(["submit_resolution", "return_resolution", "reopen"]);

export function GrievanceDetailPage() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const detail = useApi<Detail>(`/grievances/${id}`);
  const history = useApi<History>(`/grievances/${id}/history`);
  const canAi = detail.data?.allowed_actions !== undefined;
  const intel = useApi<Intel>(canAi ? `/grievances/${id}/intelligence` : null);
  const [tab, setTab] = useState("overview");
  const [dialog, setDialog] = useState<string | null>(null);
  const [message, setMessage] = useState<{ tone: "success" | "danger"; text: string } | null>(null);

  const refresh = () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0] ?? "").startsWith(`/grievances/${id}`) });
  const done = (text: string) => {
    setDialog(null);
    setMessage({ tone: "success", text });
    void refresh();
  };
  const failed = (err: unknown) => setMessage({ tone: "danger", text: errorMessage(err) });

  if (detail.isLoading) return <LoadingState label="Loading grievance…" />;
  if (detail.isError || !detail.data) return <ErrorState message={errorMessage(detail.error)} />;
  const g = detail.data;
  const acts = new Set(g.allowed_actions);
  const loc = [g.ward?.name, g.municipality?.name, g.village?.name, g.gram_panchayat?.name, g.block?.name, g.subdivision?.name, g.district?.name].filter(Boolean).join(", ");

  return (
    <>
      <PageHeader title={`${g.reference_no}: ${g.subject}`}
        description={`Registered ${formatShortIST(g.registered_at)} IST via ${g.source?.name ?? "unknown source"}`} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StatusBadge tone={STATUS_TONE[g.status]}>{STATUS_LABELS[g.status] ?? g.status}</StatusBadge>
        <StatusBadge tone={g.priority === "urgent" ? "danger" : g.priority === "high" ? "warning" : "neutral"}>{`Priority: ${titleCase(g.priority)}`}</StatusBadge>
        {g.risk ? <StatusBadge tone={RISK_TONE[g.risk.level]}>{`Risk: ${titleCase(g.risk.level)}`}</StatusBadge> : null}
        {g.overdue ? <StatusBadge tone="danger">Overdue</StatusBadge> : null}
        {g.escalation_level ? <StatusBadge tone="warning">{`Escalation level ${g.escalation_level}`}</StatusBadge> : null}
        {g.duplicate_of_id ? <Link to={`/grievances/${g.duplicate_of_id}`}>Marked as duplicate of another grievance</Link> : null}
      </div>
      {message ? <Alert tone={message.tone} title={message.text} live className="mb-4" /> : null}

      {g.allowed_actions.length ? (
        <section aria-label="Actions" className="mb-5 flex flex-wrap gap-2">
          {Object.keys(TRANSITION_LABELS).filter((a) => acts.has(a)).map((a) => (
            <Button key={a} variant={a === "reopen" || a === "return_resolution" ? "secondary" : "primary"} onClick={() => setDialog(a)}>{TRANSITION_LABELS[a]}</Button>
          ))}
          {acts.has("assign") ? <Button variant="secondary" onClick={() => setDialog("assign")}>{g.assigned_officer ? "Reassign" : "Assign"}</Button> : null}
          {acts.has("escalate") ? <Button variant="secondary" onClick={() => setDialog("escalate")}>Escalate</Button> : null}
          {acts.has("edit") ? <Button variant="secondary" onClick={() => setDialog("edit")}>Edit classification</Button> : null}
          {acts.has("comment") ? <Button variant="secondary" onClick={() => setDialog("comment")}>Add note</Button> : null}
          {acts.has("attach") ? <Button variant="secondary" onClick={() => setDialog("attach")}>Upload attachment</Button> : null}
          {acts.has("link") ? <Button variant="quiet" onClick={() => setDialog("link")}>Link grievance</Button> : null}
        </section>
      ) : null}

      <Tabs label="Grievance sections" active={tab} onChange={setTab} items={[
        { id: "overview", label: "Overview", content: <Overview g={g} loc={loc} /> },
        { id: "history", label: "History", content: <HistoryView h={history.data} loading={history.isLoading} /> },
        { id: "intel", label: "AI suggestions", content: <IntelView data={intel.data} loading={intel.isLoading} canReview={acts.has("review_ai")} onDone={done} onError={failed} /> },
        { id: "files", label: `Attachments (${history.data?.attachments.length ?? 0})`, content: <Files id={id} h={history.data} /> },
      ]} />

      {dialog && dialog in TRANSITION_LABELS ? (
        <TransitionDialog action={dialog} g={g} onClose={() => setDialog(null)} onDone={done} onError={failed} />
      ) : null}
      <AssignDialog open={dialog === "assign"} g={g} onClose={() => setDialog(null)} onDone={done} onError={failed} />
      <ReasonDialog open={dialog === "escalate"} title="Escalate grievance" label="Reason for escalation" minLength={10}
        onClose={() => setDialog(null)} onSubmit={(reason) => apiSend("POST", `/grievances/${id}/escalate`, { reason, version: g.version }).then(() => done("Grievance escalated."))} onError={failed} />
      <CommentDialog open={dialog === "comment"} id={id} onClose={() => setDialog(null)} onDone={done} onError={failed} />
      <AttachDialog open={dialog === "attach"} id={id} onClose={() => setDialog(null)} onDone={done} onError={failed} />
      <EditDialog open={dialog === "edit"} g={g} onClose={() => setDialog(null)} onDone={done} onError={failed} />
      <LinkDialog open={dialog === "link"} id={id} onClose={() => setDialog(null)} onDone={done} onError={failed} />
    </>
  );
}

function Overview({ g, loc }: { g: Detail; loc: string }) {
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
      <Panel title="Complaint">
        <p className="mt-0 whitespace-pre-wrap">{g.description}</p>
        {g.summary ? <p className="text-sm text-ink-muted"><strong>Automatic extractive summary:</strong> {g.summary}</p> : null}
        {g.resolution_summary ? <Alert tone="success" title="Latest resolution report">{g.resolution_summary}</Alert> : null}
      </Panel>
      <Panel title="Details">
        <DescriptionList items={[
          ["Category", g.category?.name ?? "Not classified"],
          ["Subcategory", g.subcategory?.name ?? "-"],
          ["Department", g.department?.name ?? "Not assigned"],
          ["Assigned officer", g.assigned_officer?.name ?? "Not assigned"],
          ["Location", loc || "Not specified"],
          ["Address / landmark", g.location_text ?? "-"],
          ["Received", `${formatShortIST(g.received_at)} IST`],
          ["Due", g.due_at ? `${formatShortIST(g.due_at)} IST` : "No time limit configured"],
          ["Reopened", String(g.reopened_count)],
          ["Registered by", g.created_by?.name ?? "Import / system"],
        ]} />
      </Panel>
      <Panel title="Complainant">
        {g.complainant ? (
          <>
            {g.complainant.masked ? <Alert tone="info" title="Personal details are restricted for your role." className="mb-3" /> : null}
            <DescriptionList items={[["Name", g.complainant.name ?? "-"], ["Mobile", g.complainant.mobile ?? "-"], ["Email", g.complainant.email ?? "-"],
              ["Address", g.complainant.address ?? "-"], ["Consent recorded", g.complainant.consent_recorded ? "Yes" : "No"]]} />
          </>
        ) : <EmptyState title="No complainant details recorded" />}
      </Panel>
      <Panel title="Risk assessment" description={g.risk ? `Risk model version ${g.risk.model_version}, assessed ${formatShortIST(g.risk.assessed_at)}` : undefined}>
        {g.risk ? (
          g.risk.factors.length ? (
            <ul className="m-0 pl-5">{g.risk.factors.map((f) => <li key={f.factor}>{f.detail} <span className="text-ink-muted">(+{f.points})</span></li>)}</ul>
          ) : <p className="m-0">No risk factors present (score {g.risk.score}).</p>
        ) : <EmptyState title="Not yet assessed" />}
        {g.escalations.length ? (
          <>
            <h3 className="mb-1 text-base">Escalations</h3>
            <ul className="m-0 pl-5">{g.escalations.map((e, i) => <li key={i}>Level {e.level} ({e.trigger === "sla_breach" ? "automatic, time limit exceeded" : "manual"}), {formatShortIST(e.created_at)}: {e.reason}</li>)}</ul>
          </>
        ) : null}
      </Panel>
    </div>
  );
}

function HistoryView({ h, loading }: { h: History | undefined; loading: boolean }) {
  if (loading || !h) return <LoadingState />;
  return (
    <div className="grid grid-cols-1 gap-5">
      <Panel title="Status history" description="Complete and unalterable record of status changes">
        <ol className="m-0 list-none p-0">
          {h.status_history.map((s, i) => (
            <li key={i} className="border-l-4 border-brand py-2 pl-3">
              <strong>{STATUS_LABELS[s.to_status] ?? s.to_status}</strong> <span className="text-ink-muted">({titleCase(s.action)})</span><br />
              <span className="text-sm">{formatShortIST(s.occurred_at)} IST by {s.actor ?? "system"}</span>
              {s.reason ? <p className="m-0 text-sm">{s.reason}</p> : null}
            </li>
          ))}
        </ol>
      </Panel>
      <Panel title="Assignments">
        <DataTable caption="Assignment history" rows={h.assignments} rowKey={(a) => a.assigned_at} emptyTitle="Never assigned"
          columns={[{ key: "o", header: "Officer", render: (a) => a.officer }, { key: "b", header: "Assigned by", render: (a) => a.assigned_by },
            { key: "from", header: "From", render: (a) => formatShortIST(a.assigned_at) }, { key: "to", header: "Until", render: (a) => (a.ended_at ? formatShortIST(a.ended_at) : "Current") }]} />
      </Panel>
      <Panel title="Notes and reports">
        {h.comments.length ? (
          <ul className="m-0 list-none p-0">{h.comments.map((c) => (
            <li key={c.id} className="border-b border-line py-2">
              <strong>{c.author}</strong> <span className="text-sm text-ink-muted">{titleCase(c.kind)}, {formatShortIST(c.created_at)}</span>
              <p className="m-0 whitespace-pre-wrap">{c.body}</p>
            </li>))}
          </ul>
        ) : <EmptyState title="No notes yet" />}
      </Panel>
    </div>
  );
}

function IntelView({ data, loading, canReview, onDone, onError }: { data: Intel | undefined; loading: boolean; canReview: boolean; onDone: (t: string) => void; onError: (e: unknown) => void }) {
  if (loading) return <LoadingState />;
  if (!data) return <EmptyState title="AI suggestions are not available for your role" />;
  const review = (c: Classification, decision: string) =>
    apiSend("POST", `/intelligence/classifications/${c.id}/review`, { decision }).then(() => onDone(`Suggestion ${decision}ed.`), onError);
  const relevant = data.classifications.filter((c) => c.verification_status !== "not_applicable" || c.processing_status !== "completed");
  return (
    <div className="grid grid-cols-1 gap-5">
      <Alert tone="info" title="Suggestions only">{data.notice}</Alert>
      <Panel title="Suggestions">
        <DataTable<Classification> caption="AI suggestions" rows={relevant} rowKey={(c) => c.id} emptyTitle="No suggestions yet. Analysis runs shortly after registration."
          columns={[
            { key: "task", header: "Task", render: (c) => titleCase(c.task) },
            { key: "pred", header: "Suggestion", render: (c) => c.processing_status === "completed"
              ? String(c.prediction.category_name ?? c.prediction.name ?? c.prediction.summary ?? c.prediction.department_id ?? "-")
              : <span className="text-ink-muted">{titleCase(c.processing_status)}</span> },
            { key: "conf", header: "Confidence", render: (c) => (c.confidence === null ? "n/a" : `${Math.round(c.confidence * 100)}%`) },
            { key: "ev", header: "Evidence", render: (c) => <code className="text-xs break-all">{JSON.stringify(c.evidence)}</code> },
            { key: "model", header: "Model", render: (c) => `${c.model_id} v${c.model_version}` },
            { key: "state", header: "Review", render: (c) =>
              c.verification_status === "pending" && canReview && c.task !== "summary" ? (
                <span className="flex gap-1">
                  <Button size="sm" onClick={() => void review(c, "accept")}>Accept</Button>
                  <Button size="sm" variant="secondary" onClick={() => void review(c, "reject")}>Reject</Button>
                </span>
              ) : `${titleCase(c.verification_status)}${c.verified_by ? ` by ${c.verified_by}` : ""}` },
          ]} />
      </Panel>
      <Panel title="Possible duplicates">
        <DataTable caption="Possible duplicates" rows={data.duplicates} rowKey={(d) => d.id} emptyTitle="No possible duplicates found"
          columns={[
            { key: "ref", header: "Grievance", render: (d) => <Link to={`/grievances/${d.candidate_grievance_id}`}>{d.reference_no}</Link> },
            { key: "s", header: "Subject", render: (d) => d.subject },
            { key: "sim", header: "Similarity", render: (d) => `${Math.round(d.similarity * 100)}%` },
            { key: "r", header: "Review", render: (d) => d.review_status === "pending" && canReview ? (
              <span className="flex gap-1">
                <Button size="sm" onClick={() => apiSend("POST", `/intelligence/duplicates/${d.id}/review`, { confirm: true }).then(() => onDone("Marked as duplicate."), onError)}>Confirm duplicate</Button>
                <Button size="sm" variant="secondary" onClick={() => apiSend("POST", `/intelligence/duplicates/${d.id}/review`, { confirm: false }).then(() => onDone("Candidate dismissed."), onError)}>Not a duplicate</Button>
              </span>) : titleCase(d.review_status) },
          ]} />
      </Panel>
    </div>
  );
}

function Files({ id, h }: { id: string; h: History | undefined }) {
  if (!h) return <LoadingState />;
  return (
    <div className="grid grid-cols-1 gap-5">
      <DataTable caption="Attachments" rows={h.attachments} rowKey={(a) => a.id} emptyTitle="No attachments"
        columns={[
          { key: "f", header: "File", render: (a) => (a.scan_status === "clean" || a.scan_status === "not_scanned"
            ? <a href={`${API_BASE}/grievances/${id}/attachments/${a.id}`} download>{a.filename}</a> : a.filename) },
          { key: "s", header: "Size", render: (a) => formatBytes(a.size_bytes) },
          { key: "scan", header: "Malware scan", render: (a) => <StatusBadge tone={a.scan_status === "clean" ? "success" : a.scan_status === "not_scanned" ? "warning" : "danger"}>{a.scan_status === "not_scanned" ? "Not scanned (development)" : titleCase(a.scan_status)}</StatusBadge> },
          { key: "u", header: "Uploaded", render: (a) => formatShortIST(a.uploaded_at) },
        ]} />
      <Panel title="External references">
        {h.external_references.length ? <ul className="m-0 pl-5">{h.external_references.map((e) => <li key={e.external_id}>{e.external_id}</li>)}</ul> : <EmptyState title="None" />}
      </Panel>
      <Panel title="Linked grievances">
        {h.relationships.length ? <ul className="m-0 pl-5">{h.relationships.map((r) => <li key={r.related_grievance_id}>{titleCase(r.relation_type)}: <Link to={`/grievances/${r.related_grievance_id}`}>open</Link>{r.note ? ` (${r.note})` : ""}</li>)}</ul> : <EmptyState title="None" />}
      </Panel>
    </div>
  );
}

type DialogProps = { onClose: () => void; onDone: (t: string) => void; onError: (e: unknown) => void };

function TransitionDialog({ action, g, onClose, onDone, onError }: { action: string; g: Detail } & DialogProps) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | undefined>();
  const need = NOTE_REQUIRED.has(action);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (need && note.trim().length < 10) {
      setErr("Please give at least 10 characters.");
      return;
    }
    setBusy(true);
    try {
      await apiSend("POST", `/grievances/${g.id}/transition`, { action, version: g.version, note: note || null });
      onDone(`${TRANSITION_LABELS[action]}: done.`);
    } catch (ex) {
      onError(ex);
      onClose();
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open title={TRANSITION_LABELS[action] ?? action} onClose={onClose}>
      <form onSubmit={submit} noValidate>
        <TextAreaField label={action === "submit_resolution" ? "Action taken (resolution report)" : need ? "Reason" : "Note (optional)"} required={need}
          value={note} onChange={(e) => setNote(e.target.value)} error={err} />
        <Button type="submit" busy={busy}>Confirm</Button>
      </form>
    </Dialog>
  );
}

function AssignDialog({ open, g, onClose, onDone, onError }: { open: boolean; g: Detail } & DialogProps) {
  const officers = useApi<Array<{ id: string; full_name: string; designation: string | null; department: string | null; same_department: boolean }>>(open ? `/grievances/${g.id}/officers` : null);
  const [officer, setOfficer] = useState("");
  const [reason, setReason] = useState("");
  const sorted = [...(officers.data ?? [])].sort((a, b) => Number(b.same_department) - Number(a.same_department));
  return (
    <Dialog open={open} title={g.assigned_officer ? "Reassign grievance" : "Assign grievance"} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); if (officer) apiSend("POST", `/grievances/${g.id}/assign`, { officer_id: officer, version: g.version, reason: reason || null }).then(() => onDone("Assigned."), onError); }} noValidate>
        <SelectField label="Officer" required options={sorted.map((o) => ({ value: o.id, label: `${o.full_name}${o.department ? `, ${o.department}` : ""}${o.same_department ? " (same department)" : ""}` }))}
          value={officer} onChange={(e) => setOfficer(e.target.value)} />
        <TextAreaField label="Instructions or reason (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
        <Button type="submit" disabled={!officer}>Assign</Button>
      </form>
    </Dialog>
  );
}

function ReasonDialog({ open, title, label, minLength, onClose, onSubmit, onError }: { open: boolean; title: string; label: string; minLength: number; onClose: () => void; onSubmit: (r: string) => Promise<unknown>; onError: (e: unknown) => void }) {
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | undefined>();
  return (
    <Dialog open={open} title={title} onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); if (reason.trim().length < minLength) { setErr(`Please give at least ${minLength} characters.`); return; } onSubmit(reason).catch(onError); }} noValidate>
        <TextAreaField label={label} required value={reason} onChange={(e) => setReason(e.target.value)} error={err} />
        <Button type="submit">Confirm</Button>
      </form>
    </Dialog>
  );
}

function CommentDialog({ open, id, onClose, onDone, onError }: { open: boolean; id: string } & DialogProps) {
  const [kind, setKind] = useState("comment");
  const [body, setBody] = useState("");
  return (
    <Dialog open={open} title="Add note" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); if (body.trim()) apiSend("POST", `/grievances/${id}/comments`, { kind, body }).then(() => { setBody(""); onDone("Note added."); }, onError); }} noValidate>
        <SelectField label="Type" options={[{ value: "comment", label: "Comment" }, { value: "investigation", label: "Investigation record" }]} placeholder="Comment" value={kind} onChange={(e) => setKind(e.target.value || "comment")} />
        <TextAreaField label="Note" required value={body} onChange={(e) => setBody(e.target.value)} />
        <Button type="submit">Save note</Button>
      </form>
    </Dialog>
  );
}

function AttachDialog({ open, id, onClose, onDone, onError }: { open: boolean; id: string } & DialogProps) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Dialog open={open} title="Upload attachment" onClose={onClose}>
      <form onSubmit={async (e) => {
        e.preventDefault();
        if (!file) return;
        setBusy(true);
        const fd = new FormData();
        fd.append("file", file);
        try { await apiSend("POST", `/grievances/${id}/attachments`, fd); onDone("File uploaded."); } catch (ex) { onError(ex); onClose(); } finally { setBusy(false); }
      }}>
        <label htmlFor="attachment-file" className="block font-semibold">File</label>
        <p id="attachment-hint" className="m-0 text-sm text-ink-muted">PDF, PNG or JPEG, up to 10 MB. Files are scanned for malware.</p>
        <input id="attachment-file" type="file" accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg" aria-describedby="attachment-hint"
          className="my-3 block" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button type="submit" busy={busy} disabled={!file}>Upload</Button>
      </form>
    </Dialog>
  );
}

function EditDialog({ open, g, onClose, onDone, onError }: { open: boolean; g: Detail } & DialogProps) {
  const cats = useCategories();
  const deps = useDepartments();
  const [v, setV] = useState({ category_id: g.category?.id ?? "", department_id: g.department?.id ?? "", priority: g.priority, reason: "" });
  return (
    <Dialog open={open} title="Edit classification" onClose={onClose}>
      <form onSubmit={(e) => {
        e.preventDefault();
        const changes: Record<string, string | null> = {};
        if (v.category_id !== (g.category?.id ?? "")) changes.category_id = v.category_id || null;
        if (v.department_id !== (g.department?.id ?? "")) changes.department_id = v.department_id || null;
        if (v.priority !== g.priority) changes.priority = v.priority;
        if (!Object.keys(changes).length) { onClose(); return; }
        apiSend("PATCH", `/grievances/${g.id}`, { changes, version: g.version, reason: v.reason || null }).then(() => onDone("Changes saved."), onError);
      }} noValidate>
        <SelectField label="Category" options={options(cats.data?.filter((c) => !c.parent_id))} value={v.category_id} onChange={(e) => setV({ ...v, category_id: e.target.value })} />
        <SelectField label="Department" options={options(deps.data)} value={v.department_id} onChange={(e) => setV({ ...v, department_id: e.target.value })} />
        <SelectField label="Priority" options={["low", "normal", "high", "urgent"].map((p) => ({ value: p, label: titleCase(p) }))} value={v.priority} onChange={(e) => setV({ ...v, priority: e.target.value || g.priority })} />
        <TextField label="Reason for change" value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} />
        <Button type="submit">Save</Button>
      </form>
    </Dialog>
  );
}

function LinkDialog({ open, id, onClose, onDone, onError }: { open: boolean; id: string } & DialogProps) {
  const [ref, setRef] = useState("");
  const [relation, setRelation] = useState("related");
  const [err, setErr] = useState<string | undefined>();
  return (
    <Dialog open={open} title="Link to another grievance" onClose={onClose}>
      <form onSubmit={async (e) => {
        e.preventDefault();
        const found = await getJson<{ items: Array<{ id: string; reference_no: string }> }>("/grievances", { q: ref.trim(), limit: 1 });
        const target = found.items.find((i) => i.reference_no === ref.trim().toUpperCase());
        if (!target) { setErr("No grievance with that reference was found in your area."); return; }
        apiSend("POST", `/grievances/${id}/links`, { related_grievance_id: target.id, relation_type: relation }).then(() => onDone("Linked."), onError);
      }} noValidate>
        <TextField label="Reference number" hint="For example DGI/2026/000123" value={ref} onChange={(e) => setRef(e.target.value)} error={err} />
        <SelectField label="Relationship" options={[{ value: "related", label: "Related" }, { value: "duplicate_of", label: "Duplicate of" }, { value: "follow_up", label: "Follow-up of" }]} placeholder="Related"
          value={relation} onChange={(e) => setRelation(e.target.value || "related")} />
        <Button type="submit">Link</Button>
      </form>
    </Dialog>
  );
}
