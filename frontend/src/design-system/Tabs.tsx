import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { cn } from "./cn";

export interface TabItem {
  id: string;
  label: string;
  content: ReactNode;
}

/** WAI-ARIA tabs with arrow-key navigation. */
export function Tabs({ items, active, onChange, label }: { items: TabItem[]; active: string; onChange: (id: string) => void; label: string }) {
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const onKey = (e: KeyboardEvent, index: number) => {
    const delta = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!delta && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (index + delta + items.length) % items.length;
    const item = items[next];
    if (item) {
      onChange(item.id);
      refs.current[item.id]?.focus();
    }
  };
  const current = items.find((i) => i.id === active) ?? items[0];
  return (
    <div>
      <div role="tablist" aria-label={label} className="flex flex-wrap gap-1 border-b border-line">
        {items.map((item, i) => (
          <button
            key={item.id}
            ref={(el) => {
              refs.current[item.id] = el;
            }}
            role="tab"
            type="button"
            id={`${base}-tab-${item.id}`}
            aria-selected={item.id === current?.id}
            aria-controls={`${base}-panel-${item.id}`}
            tabIndex={item.id === current?.id ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(e) => onKey(e, i)}
            className={cn(
              "-mb-px border-b-4 px-3 py-2 text-sm font-semibold",
              item.id === current?.id ? "border-brand text-brand" : "border-transparent text-ink-muted hover:text-ink",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>
      {current ? (
        <div role="tabpanel" id={`${base}-panel-${current.id}`} aria-labelledby={`${base}-tab-${current.id}`} className="pt-4">
          {current.content}
        </div>
      ) : null}
    </div>
  );
}
