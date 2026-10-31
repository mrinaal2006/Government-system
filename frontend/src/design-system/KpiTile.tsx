import { Link } from "react-router";

import { cn } from "./cn";

/** A KPI that always links to the records behind it. */
export function KpiTile({ label, value, to, emphasis }: { label: string; value: number | string; to: string; emphasis?: "danger" | "warning" }) {
  return (
    <Link
      to={to}
      className={cn(
        "block rounded-sm border border-line border-l-4 bg-surface px-4 py-3 text-ink no-underline hover:bg-brand-soft",
        emphasis === "danger" ? "border-l-danger" : emphasis === "warning" ? "border-l-warning" : "border-l-brand",
      )}
    >
      <span className="block text-sm text-ink-muted">{label}</span>
      <span className="block text-2xl font-semibold text-ink">{value}</span>
      <span className="sr-only">: view records</span>
    </Link>
  );
}
