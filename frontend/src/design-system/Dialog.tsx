import { useEffect, useId, useRef, type ReactNode } from "react";

/**
 * Modal dialog built on the native <dialog> element, which provides focus
 * containment, Escape to close and an inert background.
 */
export function Dialog({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto w-[min(40rem,calc(100vw-2rem))] rounded-sm border border-line-strong bg-surface p-0 text-ink backdrop:bg-black/50"
    >
      {open ? (
        <div className="p-5">
          <div className="mb-3 flex items-start justify-between gap-3 border-b border-line pb-2">
            <h2 id={titleId} className="m-0 text-lg font-semibold text-brand">
              {title}
            </h2>
            <button type="button" onClick={onClose} className="rounded-sm px-2 text-ink underline" aria-label="Close dialog">
              Close
            </button>
          </div>
          {children}
        </div>
      ) : null}
    </dialog>
  );
}
