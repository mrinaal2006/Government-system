import { Button } from "./Button";

export function Pagination({ total, limit, offset, onChange, label = "records" }: {
  total: number; limit: number; offset: number; onChange: (offset: number) => void; label?: string;
}) {
  if (total === 0) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <nav aria-label="Pagination" className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
      <p className="m-0 text-ink-muted" aria-live="polite">
        Showing {from}-{to} of {total} {label}
      </p>
      <div className="flex gap-2">
        <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          Previous
        </Button>
        <Button variant="secondary" size="sm" disabled={to >= total} onClick={() => onChange(offset + limit)}>
          Next
        </Button>
      </div>
    </nav>
  );
}
