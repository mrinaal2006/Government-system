import { Alert, Button, DataTable, ErrorState, LoadingState, PageHeader, Panel, StatusBadge, type Column } from "@/design-system";
import { ApiError } from "@/lib/api/client";
import { useReadiness, useSystemInfo, type ComponentStatus } from "@/lib/api/system";
import { formatDateTimeIST } from "@/lib/format";

const COMPONENT_LABELS: Record<string, string> = {
  database: "PostgreSQL database",
  postgis: "PostGIS spatial extension",
  migrations: "Database schema version",
  redis: "Redis (cache and task queue)",
};

const REASON_LABELS: Record<string, string> = {
  unreachable: "Service could not be reached",
  timeout: "Check timed out",
  schema_not_at_head: "Database migrations are pending",
  extension_missing: "Extension not installed",
  database_unavailable: "Not checked: database unavailable",
  no_pong: "Unexpected response",
};

type Row = { name: string } & ComponentStatus;

const columns: Column<Row>[] = [
  { key: "name", header: "Component", render: (r) => COMPONENT_LABELS[r.name] ?? r.name },
  {
    key: "status",
    header: "Status",
    render: (r) => <StatusBadge tone={r.status === "ok" ? "success" : "danger"}>{r.status === "ok" ? "Operational" : "Unavailable"}</StatusBadge>,
  },
  { key: "latency", header: "Response time", align: "right", render: (r) => `${r.latency_ms.toFixed(1)} ms` },
  { key: "detail", header: "Detail", render: (r) => (r.reason ? (REASON_LABELS[r.reason] ?? r.reason) : "None") },
];

export function SystemStatusPage() {
  const readiness = useReadiness();
  const info = useSystemInfo();
  const rows: Row[] | undefined = readiness.data
    ? Object.entries(readiness.data.components).map(([name, c]) => ({ name, ...c }))
    : undefined;
  const err = readiness.error instanceof ApiError ? readiness.error : null;

  return (
    <>
      <PageHeader
        title="System status"
        description="Live readiness of the services this application depends on. Checked automatically every 30 seconds."
        actions={
          <Button variant="secondary" busy={readiness.isFetching} busyLabel="Checking…" onClick={() => void readiness.refetch()}>
            Check now
          </Button>
        }
      />
      <div className="grid grid-cols-1 gap-5">
        {readiness.data ? (
          readiness.data.status === "ok" ? (
            <Alert tone="success" title="All services are operational" live>
              Last checked {formatDateTimeIST(readiness.data.checked_at)}.
            </Alert>
          ) : (
            <Alert tone="danger" title="One or more services are unavailable">
              Last checked {formatDateTimeIST(readiness.data.checked_at)}. Inform the district IT cell if this persists.
            </Alert>
          )
        ) : null}

        <Panel title="Service readiness" description="Source: /api/v1/health/ready">
          <DataTable
            caption="Service readiness"
            columns={columns}
            rows={rows}
            rowKey={(r) => r.name}
            loading={readiness.isLoading}
            error={
              readiness.isError
                ? {
                    message: err?.message ?? "Readiness information could not be loaded.",
                    requestId: err?.requestId,
                    onRetry: () => void readiness.refetch(),
                  }
                : null
            }
            emptyTitle="No components reported"
          />
        </Panel>

        <Panel title="Application" description="Source: /api/v1/system/info">
          {info.isLoading ? (
            <LoadingState label="Loading application details…" />
          ) : info.isError ? (
            <ErrorState message="Application details could not be loaded." onRetry={() => void info.refetch()} />
          ) : info.data ? (
            <dl className="m-0 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-[max-content_1fr]">
              <dt className="font-semibold">Application</dt>
              <dd className="m-0">{info.data.application}</dd>
              <dt className="font-semibold">Version</dt>
              <dd className="m-0">{info.data.version}</dd>
              <dt className="font-semibold">Environment</dt>
              <dd className="m-0 capitalize">{info.data.environment}</dd>
              <dt className="font-semibold">District</dt>
              <dd className="m-0">{info.data.deployment.district_name ?? "Not configured (set DEPLOYMENT_DISTRICT_NAME)"}</dd>
            </dl>
          ) : null}
        </Panel>
      </div>
    </>
  );
}
