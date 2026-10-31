import type { ReactNode } from "react";

import { cn } from "./cn";

export type Tone = "info" | "success" | "warning" | "danger";

const tones: Record<Tone, { box: string; label: string }> = {
  info: { box: "border-brand bg-brand-soft text-ink", label: "Information" },
  success: { box: "border-success bg-success-soft text-ink", label: "Success" },
  warning: { box: "border-warning bg-warning-soft text-ink", label: "Warning" },
  danger: { box: "border-danger bg-danger-soft text-ink", label: "Error" },
};

export interface AlertProps {
  tone?: Tone;
  title: string;
  children?: ReactNode;
  /** Announce to assistive technology when the alert appears. Errors default to assertive. */
  live?: boolean;
  className?: string;
}

export function Alert({ tone = "info", title, children, live, className }: AlertProps) {
  const t = tones[tone];
  const role = live === false ? undefined : tone === "danger" ? "alert" : live ? "status" : undefined;
  return (
    <div role={role} className={cn("rounded-sm border-l-4 border px-4 py-3", t.box, className)}>
      <p className="m-0 font-semibold">
        <span className="sr-only">{t.label}: </span>
        {title}
      </p>
      {children ? <div className="mt-1 text-sm text-ink">{children}</div> : null}
    </div>
  );
}
