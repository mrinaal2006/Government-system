import type { ReactNode } from "react";

export function DescriptionList({ items }: { items: Array<[string, ReactNode]> }) {
  return (
    <dl className="m-0 grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-[max-content_1fr]">
      {items.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="font-semibold text-ink">{k}</dt>
          <dd className="m-0 text-ink">{v ?? "-"}</dd>
        </div>
      ))}
    </dl>
  );
}
