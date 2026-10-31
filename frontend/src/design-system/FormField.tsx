import {
  useId,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";

import { cn } from "./cn";

interface FieldFrameProps {
  label: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: (ids: { inputId: string; describedBy: string | undefined; invalid: boolean }) => ReactNode;
}

/**
 * Accessible field wrapper: visible <label>, hint and error text linked through
 * aria-describedby, aria-invalid on error, and a textual "(required)" marker
 * rather than a colour-only asterisk.
 */
function FieldFrame({ label, hint, error, required, children }: FieldFrameProps) {
  const base = useId();
  const inputId = `${base}-input`;
  const hintId = hint ? `${base}-hint` : undefined;
  const errorId = error ? `${base}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className={cn("mb-4", error && "border-l-4 border-danger pl-3")}>
      <label htmlFor={inputId} className="block font-semibold text-ink">
        {label}
        {required ? <span className="font-normal text-ink-muted"> (required)</span> : null}
      </label>
      {hint ? (
        <p id={hintId} className="m-0 text-sm text-ink-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="m-0 mt-0.5 text-sm font-semibold text-danger">
          <span className="sr-only">Error: </span>
          {error}
        </p>
      ) : null}
      <div className="mt-1">{children({ inputId, describedBy, invalid: Boolean(error) })}</div>
    </div>
  );
}

const control =
  "block w-full max-w-xl rounded-sm border border-line-strong bg-surface px-3 py-2 text-base text-ink " +
  "aria-[invalid=true]:border-2 aria-[invalid=true]:border-danger disabled:bg-surface-muted";

type Common = { label: string; hint?: string; error?: string };

export function TextField({ label, hint, error, required, className, ...rest }: Common & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <FieldFrame label={label} hint={hint} error={error} required={required}>
      {({ inputId, describedBy, invalid }) => (
        <input
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(control, className)}
          {...rest}
        />
      )}
    </FieldFrame>
  );
}

export function TextAreaField({ label, hint, error, required, className, ...rest }: Common & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <FieldFrame label={label} hint={hint} error={error} required={required}>
      {({ inputId, describedBy, invalid }) => (
        <textarea
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(control, "min-h-28", className)}
          {...rest}
        />
      )}
    </FieldFrame>
  );
}

export interface SelectOption {
  value: string;
  label: string;
}

export function SelectField({
  label,
  hint,
  error,
  required,
  options,
  placeholder = "Select an option",
  className,
  ...rest
}: Common & SelectHTMLAttributes<HTMLSelectElement> & { options: SelectOption[]; placeholder?: string }) {
  return (
    <FieldFrame label={label} hint={hint} error={error} required={required}>
      {({ inputId, describedBy, invalid }) => (
        <select
          id={inputId}
          aria-describedby={describedBy}
          aria-invalid={invalid || undefined}
          required={required}
          className={cn(control, className)}
          {...rest}
        >
          <option value="">{placeholder}</option>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      )}
    </FieldFrame>
  );
}
