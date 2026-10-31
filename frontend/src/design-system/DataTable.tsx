import type { ReactNode } from "react";

import { cn } from "./cn";
import { EmptyState, ErrorState, LoadingState } from "./States";

export type SortDirection = "ascending" | "descending";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  sortable?: boolean;
  align?: "left" | "right";
}

export interface DataTableProps<T> {
  /** Required: a visible caption describing the table (WCAG 1.3.1). */
  caption: string;
  columns: Column<T>[];
  rows: T[] | undefined;
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: { message: string; requestId?: string | null; onRetry?: () => void } | null;
  emptyTitle?: string;
  emptyMessage?: ReactNode;
  sort?: { key: string; direction: SortDirection } | null;
  onSortChange?: (key: string, direction: SortDirection) => void;
}

/**
 * Server-driven data table. Sorting is reported to the caller (the server sorts
 * and paginates); the table only renders. Loading, error and empty states are
 * part of the component so no screen can omit them.
 */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  loading = false,
  error = null,
  emptyTitle = "No records found",
  emptyMessage,
  sort = null,
  onSortChange,
}: DataTableProps<T>) {
  if (error) return <ErrorState message={error.message} requestId={error.requestId} onRetry={error.onRetry} />;
  if (loading && !rows) return <LoadingState label={`Loading ${caption.toLowerCase()}…`} />;
  if (!rows || rows.length === 0) return <EmptyState title={emptyTitle}>{emptyMessage}</EmptyState>;

  return (
    <div className="overflow-x-auto rounded-sm border border-line" role="region" aria-label={`${caption} (scrollable table)`} tabIndex={0}>
      <table className="w-full border-collapse text-left text-sm" aria-busy={loading || undefined}>
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-brand-soft">
          <tr>
            {columns.map((col) => {
              const active = sort?.key === col.key;
              const ariaSort = active ? sort.direction : col.sortable ? "none" : undefined;
              const next: SortDirection = active && sort.direction === "ascending" ? "descending" : "ascending";
              return (
                <th
                  key={col.key}
                  scope="col"
                  aria-sort={ariaSort}
                  className={cn(
                    "border-b-2 border-brand px-3 py-2 font-semibold text-brand",
                    col.align === "right" && "text-right",
                  )}
                >
                  {col.sortable && onSortChange ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 font-semibold text-brand underline"
                      onClick={() => onSortChange(col.key, next)}
                    >
                      {col.header}
                      <span aria-hidden="true">{active ? (sort.direction === "ascending" ? "▲" : "▼") : "↕"}</span>
                    </button>
                  ) : (
                    col.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={rowKey(row)} className="border-b border-line odd:bg-surface even:bg-surface-muted">
              {columns.map((col) => (
                <td key={col.key} className={cn("px-3 py-2 align-top text-ink", col.align === "right" && "text-right")}>
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
