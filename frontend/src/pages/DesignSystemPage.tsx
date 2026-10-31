import { useState } from "react";

import {
  Alert,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  Panel,
  SelectField,
  StatusBadge,
  TextAreaField,
  TextField,
  type SortDirection,
} from "@/design-system";

/**
 * DEVELOPMENT-ONLY component reference (route registered only when
 * import.meta.env.DEV). The sample content is illustrative and labelled as such;
 * it is never shown in a production build.
 */
type SampleRow = { id: string; label: string; status: string };
const SAMPLE_ROWS: SampleRow[] = [
  { id: "1", label: "Sample row A (illustrative)", status: "Open" },
  { id: "2", label: "Sample row B (illustrative)", status: "Closed" },
];

export function DesignSystemPage() {
  const [sort, setSort] = useState<{ key: string; direction: SortDirection }>({ key: "label", direction: "ascending" });
  const rows = [...SAMPLE_ROWS].sort((a, b) => (sort.direction === "ascending" ? 1 : -1) * a.label.localeCompare(b.label));
  return (
    <>
      <PageHeader title="Design system reference" description="Development-only catalogue of interface components." />
      <div className="grid grid-cols-1 gap-5">
        <Alert tone="warning" title="Illustrative content only">
          Everything on this page is sample content for developers. It is not operational data.
        </Alert>
        <Panel title="Buttons">
          <div className="flex flex-wrap gap-2">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="quiet">Quiet</Button>
            <Button busy>Saving</Button>
          </div>
        </Panel>
        <Panel title="Alerts and badges">
          <div className="grid grid-cols-1 gap-2">
            <Alert tone="info" title="Information alert" />
            <Alert tone="success" title="Success alert" />
            <Alert tone="warning" title="Warning alert" />
            <Alert tone="danger" title="Error alert" live={false} />
            <div className="flex gap-2">
              <StatusBadge>Neutral</StatusBadge>
              <StatusBadge tone="info">Info</StatusBadge>
              <StatusBadge tone="success">Success</StatusBadge>
              <StatusBadge tone="warning">Warning</StatusBadge>
              <StatusBadge tone="danger">Danger</StatusBadge>
            </div>
          </div>
        </Panel>
        <Panel title="Form fields">
          <TextField label="Text field" hint="Hint text explains the expected format." required />
          <TextField label="Field with error" error="Enter a value in the correct format." defaultValue="bad" />
          <SelectField label="Select field" options={[{ value: "a", label: "Option A" }, { value: "b", label: "Option B" }]} />
          <TextAreaField label="Text area" />
        </Panel>
        <Panel title="Data table">
          <DataTable
            caption="Sample table"
            columns={[
              { key: "label", header: "Label", sortable: true, render: (r: SampleRow) => r.label },
              { key: "status", header: "Status", render: (r: SampleRow) => r.status },
            ]}
            rows={rows}
            rowKey={(r) => r.id}
            sort={sort}
            onSortChange={(key, direction) => setSort({ key, direction })}
          />
        </Panel>
        <Panel title="States">
          <div className="grid grid-cols-1 gap-3">
            <LoadingState />
            <EmptyState title="Empty state">Explains why nothing is shown and what to do next.</EmptyState>
            <ErrorState message="Error state with a reference ID." requestId="0123456789abcdef" />
          </div>
        </Panel>
      </div>
    </>
  );
}
