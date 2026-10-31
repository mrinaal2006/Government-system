import type { ReactNode } from "react";

import { Button } from "./Button";

/** Polite live region: screen readers announce the loading message. No animation. */
export function LoadingState({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="rounded-sm border border-dashed border-line px-4 py-6 text-ink-muted">
      {label}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-sm border border-dashed border-line-strong bg-surface-muted px-4 py-8 text-center">
      <p className="m-0 font-semibold text-ink">{title}</p>
      {children ? <div className="mx-auto mt-1 max-w-xl text-sm text-ink-muted">{children}</div> : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export interface ErrorStateProps {
  title?: string;
  message: string;
  requestId?: string | null;
  onRetry?: () => void;
}

export function ErrorState({ title = "Something went wrong", message, requestId, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="rounded-sm border border-l-4 border-danger bg-danger-soft px-4 py-4">
      <p className="m-0 font-semibold text-danger">{title}</p>
      <p className="m-0 mt-1 text-ink">{message}</p>
      {requestId ? (
        <p className="m-0 mt-1 text-sm text-ink-muted">
          Reference for the IT cell: <code>{requestId}</code>
        </p>
      ) : null}
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
