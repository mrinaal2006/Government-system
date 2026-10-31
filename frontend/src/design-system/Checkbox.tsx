import { useId, type InputHTMLAttributes } from "react";

export function Checkbox({ label, hint, ...rest }: { label: string; hint?: string } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="mb-3 flex items-start gap-2">
      <input id={id} type="checkbox" className="mt-1 h-5 w-5 accent-[var(--color-brand)]" aria-describedby={hint ? `${id}-h` : undefined} {...rest} />
      <label htmlFor={id} className="text-ink">
        {label}
        {hint ? (
          <span id={`${id}-h`} className="block text-sm text-ink-muted">
            {hint}
          </span>
        ) : null}
      </label>
    </div>
  );
}
