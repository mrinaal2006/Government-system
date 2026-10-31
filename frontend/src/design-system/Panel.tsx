import { useId, type ReactNode } from "react";

import { cn } from "./cn";

export interface PanelProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  headingLevel?: 2 | 3;
  className?: string;
}

/** A titled content region. Rendered as a labelled <section> landmark. */
export function Panel({ title, description, actions, children, headingLevel = 2, className }: PanelProps) {
  const id = useId();
  const Heading = headingLevel === 2 ? "h2" : "h3";
  return (
    <section aria-labelledby={id} className={cn("min-w-0 rounded-sm border border-line bg-surface", className)}>
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div>
          <Heading id={id} className="m-0 text-lg font-semibold text-brand">
            {title}
          </Heading>
          {description ? <p className="m-0 mt-0.5 text-sm text-ink-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex gap-2">{actions}</div> : null}
      </header>
      <div className="p-4">{children}</div>
    </section>
  );
}
