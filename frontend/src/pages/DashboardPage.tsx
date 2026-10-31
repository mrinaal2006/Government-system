import { useState } from "react";
import { Link, Navigate } from "react-router";

import {
  Button,
  Chart,
  DataTable,
  EmptyState,
  ErrorState,
  KpiTile,
  LoadingState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/design-system";
import { toQuery } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { formatDateTimeIST, formatShortIST, RISK_TONE, STATUS_LABELS, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { visibleGroups } from "@/layout/navigation";

interface Kpi { key: string; label: string; value: number; filter?: Record<string, unknown>; link?: string }
interface PerfRow { id: string | null; name: string; received: number; open: number; resolved: number; overdue: number; sla_compliance_pct: number | null; avg_hours: number | null }
interface Cluster { id: string; category: string | null; category_id: string | null; unit_level: string; unit_id: string; unit_name: string; open_count: number; grievance_count: number }
interface Important { id: string; reference_no: string; subject: string; status: string; risk_level: string; risk_score: number; due_at: string | null }
interface Action { action: string; actor: string | null; occurred_at: string; grievance_id: string }

const EMPHASIS: Record<string, "danger" | "warning" | undefined> = { overdue: "danger", high_risk: "warning", critical_alerts: "danger" };

export function HomePage() {
  const { can } = useAuth();
  if (can("dashboard.read", "grievance.read")) return <DashboardPage />;
  const first = visibleGroups((p) => can(p)).flatMap((g) => g.items)[0];
  return <Navigate to={first && first.path !== "/" ? first.path : "/notifications"} replace />;
}

export function DashboardPage() {
  const [granularity, setGranularity] = useState<"week" | "month">("week");
  const summary = useApi<{ generated_at: string; kpis: Kpi[] }>("/dashboard/summary", undefined, { refetchInterval: 120_000 });
  const trends = useApi<{ series: Array<{ period: string; received: number; resolved: number }> }>("/dashboard/trends", { granularity });
  const blocks = useApi<PerfRow[]>("/dashboard/blocks");
  const categories = useApi<PerfRow[]>("/dashboard/categories");
  const departments = useApi<PerfRow[]>("/performance/departments");
  const clusters = useApi<Cluster[]>("/dashboard/clusters");
  const important = useApi<Important[]>("/dashboard/important");
  const actions = useApi<Action[]>("/dashboard/recent-actions");

  return (
    <>
      <PageHeader
        title="District command dashboard"
        description={summary.data ? `Live figures for your area of responsibility. Updated ${formatDateTimeIST(summary.data.generated_at)}.` : "Live figures for your area of responsibility."}
      />
      {summary.isLoading ? <LoadingState label="Loading indicators…" /> : summary.isError ? (
        <ErrorState message="Indicators could not be loaded." onRetry={() => void summary.refetch()} />
      ) : (
        <section aria-label="Key indicators" className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          {summary.data?.kpis.map((k) => (
            <KpiTile key={k.key} label={k.label} value={k.value} emphasis={EMPHASIS[k.key]}
              to={k.link ?? `/grievances${toQuery(k.filter as Record<string, unknown>)}`} />
          ))}
        </section>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        <Panel title="Grievance trend" description="Registered and resolved, by period (IST)"
          actions={
            <div role="group" aria-label="Trend period" className="flex gap-1">
              {(["week", "month"] as const).map((g) => (
                <Button key={g} size="sm" variant={granularity === g ? "primary" : "secondary"} aria-pressed={granularity === g} onClick={() => setGranularity(g)}>
                  {g === "week" ? "Weekly" : "Monthly"}
                </Button>
              ))}
            </div>
          }>
          {trends.isLoading ? <LoadingState /> : trends.data?.series.length ? (
            <Chart title="Grievance trend" categories={trends.data.series.map((s) => s.period)}
              series={[{ name: "Registered", values: trends.data.series.map((s) => s.received), type: "line" },
                       { name: "Resolved", values: trends.data.series.map((s) => s.resolved), type: "line", color: "#136b35" }]} />
          ) : <EmptyState title="No grievances in this period" />}
        </Panel>

        <Panel title="Block-wise distribution" description="Open and overdue grievances by block">
          {blocks.isLoading ? <LoadingState /> : blocks.data?.length ? (
            <Chart title="Block-wise distribution" horizontal categories={blocks.data.map((b) => b.name)}
              series={[{ name: "Open", values: blocks.data.map((b) => b.open) }, { name: "Overdue", values: blocks.data.map((b) => b.overdue), color: "#b3261e" }]} />
          ) : <EmptyState title="No grievances recorded yet" />}
        </Panel>

        <Panel title="Emerging issue clusters" description="Same category, same area, recent window">
          {clusters.data?.length ? (
            <ul className="m-0 list-none p-0">
              {clusters.data.map((c) => (
                <li key={c.id} className="flex items-center justify-between border-b border-line py-2">
                  <span>
                    <strong>{c.category ?? "Uncategorised"}</strong> in {c.unit_name} ({titleCase(c.unit_level)})
                  </span>
                  <Link to={`/grievances${toQuery({ category_id: c.category_id, [`${c.unit_level}_id`]: c.unit_id, open_only: true })}`}>
                    {c.open_count} open
                  </Link>
                </li>
              ))}
            </ul>
          ) : clusters.isLoading ? <LoadingState /> : <EmptyState title="No clusters detected" />}
        </Panel>

        <Panel title="Issue categories" description="Received grievances by category">
          {categories.data?.length ? (
            <Chart title="Issue categories" horizontal categories={categories.data.map((c) => c.name)}
              series={[{ name: "Received", values: categories.data.map((c) => c.received) }]} />
          ) : categories.isLoading ? <LoadingState /> : <EmptyState title="No data" />}
        </Panel>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-5">
        <Panel title="Important unresolved grievances" description="Open grievances assessed as high or critical risk">
          <DataTable<Important>
            caption="Important unresolved grievances" rows={important.data} rowKey={(r) => r.id} loading={important.isLoading}
            emptyTitle="No high-risk open grievances"
            columns={[
              { key: "ref", header: "Reference", render: (r) => <Link to={`/grievances/${r.id}`}>{r.reference_no}</Link> },
              { key: "subject", header: "Subject", render: (r) => r.subject },
              { key: "status", header: "Status", render: (r) => STATUS_LABELS[r.status] ?? r.status },
              { key: "risk", header: "Risk", render: (r) => <StatusBadge tone={RISK_TONE[r.risk_level]}>{`${titleCase(r.risk_level)} (${r.risk_score})`}</StatusBadge> },
              { key: "due", header: "Due (IST)", render: (r) => formatShortIST(r.due_at) },
            ]}
          />
        </Panel>
        <Panel title="Department performance">
          <DataTable<PerfRow>
            caption="Department performance" rows={departments.data} rowKey={(r) => r.id ?? "none"} loading={departments.isLoading}
            columns={[
              { key: "name", header: "Department", render: (r) => r.id ? <Link to={`/grievances?department_id=${r.id}`}>{r.name}</Link> : r.name },
              { key: "received", header: "Received", align: "right", render: (r) => r.received },
              { key: "open", header: "Open", align: "right", render: (r) => r.open },
              { key: "overdue", header: "Overdue", align: "right", render: (r) => r.id ? <Link to={`/grievances?department_id=${r.id}&overdue=true`}>{r.overdue}</Link> : r.overdue },
              { key: "sla", header: "Within SLA", align: "right", render: (r) => (r.sla_compliance_pct === null ? "n/a" : `${r.sla_compliance_pct}%`) },
              { key: "avg", header: "Avg. resolution", align: "right", render: (r) => (r.avg_hours === null ? "n/a" : `${r.avg_hours} h`) },
            ]}
          />
        </Panel>
        <Panel title="Recent administrative actions">
          {actions.data?.length ? (
            <ul className="m-0 list-none p-0 text-sm">
              {actions.data.map((a, i) => (
                <li key={`${a.grievance_id}-${i}`} className="border-b border-line py-1.5">
                  {formatShortIST(a.occurred_at)}: <strong>{a.actor ?? "system"}</strong> {titleCase(a.action.replace("grievance.", ""))}{" "}
                  <Link to={`/grievances/${a.grievance_id}`}>view grievance</Link>
                </li>
              ))}
            </ul>
          ) : actions.isLoading ? <LoadingState /> : <EmptyState title="No recent actions" />}
        </Panel>
      </div>
    </>
  );
}
