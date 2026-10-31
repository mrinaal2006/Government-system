import { cn } from "./cn";
import type { Tone } from "./Alert";

const tones: Record<Tone | "neutral", string> = {
  neutral: "border-line-strong bg-surface-muted text-ink",
  info: "border-brand bg-brand-soft text-brand",
  success: "border-success bg-success-soft text-success",
  warning: "border-warning bg-warning-soft text-warning",
  danger: "border-danger bg-danger-soft text-danger",
};

/** Status is always conveyed by text; colour is supplementary (WCAG 1.4.1). */
export function StatusBadge({ tone = "neutral", children }: { tone?: Tone | "neutral"; children: string }) {
  return (
    <span className={cn("inline-block rounded-sm border px-2 py-0.5 text-sm font-semibold", tones[tone])}>
      {children}
    </span>
  );
}
