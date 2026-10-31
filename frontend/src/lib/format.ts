/** Timestamps are stored and transmitted in UTC and shown in Indian Standard Time. */
const IST = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});
const IST_SHORT = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

export function formatDateTimeIST(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Unknown time";
  return `${IST.format(date)} IST`;
}

export function formatShortIST(iso: string | null | undefined): string {
  if (!iso) return "-";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "-" : IST_SHORT.format(date);
}

export const STATUS_LABELS: Record<string, string> = {
  registered: "Registered",
  assigned: "Assigned",
  in_progress: "In progress",
  resolution_submitted: "Resolution submitted",
  resolved: "Resolved",
  closed: "Closed",
  reopened: "Reopened",
};

export const STATUS_TONE: Record<string, "neutral" | "info" | "success" | "warning" | "danger"> = {
  registered: "neutral",
  assigned: "info",
  in_progress: "info",
  resolution_submitted: "warning",
  resolved: "success",
  closed: "success",
  reopened: "danger",
};

export const RISK_TONE: Record<string, "neutral" | "info" | "warning" | "danger"> = {
  normal: "neutral",
  watch: "info",
  high: "warning",
  critical: "danger",
};

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
