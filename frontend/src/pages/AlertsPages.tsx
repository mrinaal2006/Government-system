import { useState } from "react";
import { Link, useParams } from "react-router";

import { Alert, Button, DataTable, DescriptionList, EmptyState, ErrorState, LoadingState, PageHeader, Panel, SelectField, StatusBadge, TextAreaField } from "@/design-system";
import { apiSend, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { formatShortIST, STATUS_LABELS, titleCase } from "@/lib/format";
import { useApi, useApiMutation, useUrlFilters } from "@/lib/hooks";

interface AlertRow {
  id: string; alert_type: string; level: string; title: string; status: string; reasons: string[]; metrics: Record<string, number>;
  recommended_actions: string[]; district: string | null; block: string | null; village: string | null; category: string | null;
  department: string | null; risk_model_version: number; first_detected_at: string; last_detected_at: string; closed_at: string | null;
}
interface AlertDetail extends AlertRow {
  grievances: Array<{ id: string; reference_no: string; subject: string; status: string; due_at: string | null }>;
  actions: Array<{ action: string; reason: string; from_status: string; to_status: string; actor: string; occurred_at: string }>;
}
const LEVEL_TONE = { critical: "danger", high: "warning", watch: "info" } as const;

export function AlertsPage() {
  const { can } = useAuth();
  const [f, setF] = useUrlFilters<{ status?: string; level: string[] }>(["status", "level"], ["level"]);
  const list = useApi<{ items: AlertRow[]; total: number }>("/alerts", { status: f.status ?? "active", level: f.level, limit: 100 });
  const evaluate = useApiMutation<Record<string, never>, { evaluated: number; new_alerts: number }>("POST", "/alerts/evaluate", ["/alerts", "/dashboard"]);
  return (
    <>
      <PageHeader title="Early warning alerts" description="Explainable alerts from configurable indicators. Alerts never trigger administrative action on their own."
        actions={can("alert.act") ? <Button variant="secondary" busy={evaluate.isPending} busyLabel="Evaluating…" onClick={() => evaluate.mutate({})}>Re-evaluate now</Button> : null} />
      {evaluate.data ? <Alert tone="success" title={`Evaluation complete: ${evaluate.data.new_alerts} new alert(s).`} live className="mb-4" /> : null}
      <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
        <SelectField label="Status" placeholder="Active" options={[{ value: "active", label: "Active" }, { value: "closed", label: "Closed" }, { value: "all", label: "All" }]}
          value={f.status ?? ""} onChange={(e) => setF({ status: e.target.value || undefined })} />
        <SelectField label="Level" placeholder="Any level" options={["critical", "high", "watch"].map((l) => ({ value: l, label: titleCase(l) }))}
          value={f.level[0] ?? ""} onChange={(e) => setF({ level: e.target.value ? [e.target.value] : [] })} />
      </div>
      <DataTable<AlertRow> caption="Early warning alerts" rows={list.data?.items} rowKey={(a) => a.id} loading={list.isLoading}
        error={list.isError ? { message: errorMessage(list.error) } : null} emptyTitle="No alerts match"
        columns={[
          { key: "level", header: "Level", render: (a) => <StatusBadge tone={LEVEL_TONE[a.level as keyof typeof LEVEL_TONE]}>{titleCase(a.level)}</StatusBadge> },
          { key: "title", header: "Alert", render: (a) => <Link to={`/early-warning/${a.id}`}>{a.title}</Link> },
          { key: "type", header: "Indicator", render: (a) => titleCase(a.alert_type) },
          { key: "area", header: "Area", render: (a) => [a.village, a.block, a.district].filter(Boolean).join(", ") || a.department || "-" },
          { key: "status", header: "Status", render: (a) => titleCase(a.status) },
          { key: "seen", header: "Last detected", render: (a) => formatShortIST(a.last_detected_at) },
        ]} />
    </>
  );
}

export function AlertDetailPage() {
  const { id = "" } = useParams();
  const { can } = useAuth();
  const alert = useApi<AlertDetail>(`/alerts/${id}`);
  const [action, setAction] = useState("acknowledge");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);
  if (alert.isLoading) return <LoadingState />;
  if (alert.isError || !alert.data) return <ErrorState message={errorMessage(alert.error)} />;
  const a = alert.data;
  const closed = a.status === "dismissed" || a.status === "resolved";
  return (
    <>
      <PageHeader title={a.title} description={`${titleCase(a.alert_type)} indicator, risk model version ${a.risk_model_version}`} />
      <div className="mb-4 flex gap-2">
        <StatusBadge tone={LEVEL_TONE[a.level as keyof typeof LEVEL_TONE]}>{`Level: ${titleCase(a.level)}`}</StatusBadge>
        <StatusBadge>{`Status: ${titleCase(a.status)}`}</StatusBadge>
      </div>
      {ok ? <Alert tone="success" title={ok} live className="mb-3" /> : null}
      {err ? <Alert tone="danger" title={err} className="mb-3" /> : null}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel title="Why this alert was raised">
          <ul className="m-0 pl-5">{a.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          <DescriptionList items={[["Area", [a.village, a.block, a.district].filter(Boolean).join(", ") || "-"], ["Category", a.category ?? "-"],
            ["Department", a.department ?? "-"], ["First detected", formatShortIST(a.first_detected_at)], ["Last detected", formatShortIST(a.last_detected_at)]]} />
        </Panel>
        <Panel title="Recommended administrative actions" description="Suggestions from configuration for consideration by the competent officer">
          <ul className="m-0 pl-5">{a.recommended_actions.map((r) => <li key={r}>{r}</li>)}</ul>
        </Panel>
        <Panel title={`Underlying grievances (${a.grievances.length})`}>
          <DataTable caption="Underlying grievances" rows={a.grievances} rowKey={(g) => g.id} emptyTitle="None visible in your area"
            columns={[{ key: "r", header: "Reference", render: (g) => <Link to={`/grievances/${g.id}`}>{g.reference_no}</Link> },
              { key: "s", header: "Subject", render: (g) => g.subject }, { key: "st", header: "Status", render: (g) => STATUS_LABELS[g.status] ?? g.status }]} />
        </Panel>
        <Panel title="Officer actions">
          {a.actions.length ? (
            <ol className="m-0 pl-5">{a.actions.map((x, i) => <li key={i}>{formatShortIST(x.occurred_at)}: <strong>{x.actor}</strong> {titleCase(x.action)} ({titleCase(x.from_status)} → {titleCase(x.to_status)}): {x.reason}</li>)}</ol>
          ) : <EmptyState title="No actions recorded yet" />}
          {can("alert.act") ? (
            <form className="mt-4" noValidate onSubmit={(e) => {
              e.preventDefault();
              setErr(null);
              if (reason.trim().length < 5) { setErr("A reason of at least 5 characters is required."); return; }
              apiSend("POST", `/alerts/${id}/actions`, { action, reason }).then(() => { setOk("Action recorded."); setReason(""); void alert.refetch(); }, (ex) => setErr(errorMessage(ex)));
            }}>
              <SelectField label="Action" options={(closed ? ["comment"] : ["acknowledge", "investigate", "escalate", "dismiss", "resolve", "comment"]).map((x) => ({ value: x, label: titleCase(x) }))}
                value={action} onChange={(e) => setAction(e.target.value || "acknowledge")} />
              <TextAreaField label="Reason" required value={reason} onChange={(e) => setReason(e.target.value)} />
              <Button type="submit">Record action</Button>
            </form>
          ) : null}
        </Panel>
      </div>
    </>
  );
}
