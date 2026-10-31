import type { ButtonHTMLAttributes } from "react";

import { cn } from "./cn";

export type ButtonVariant = "primary" | "secondary" | "danger" | "quiet";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-brand text-on-brand border-brand hover:bg-brand-hover",
  secondary: "bg-surface text-brand border-brand hover:bg-brand-soft",
  danger: "bg-danger text-on-brand border-danger hover:opacity-90",
  quiet: "bg-transparent text-link border-transparent underline hover:bg-brand-soft",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md";
  /** Shows a busy label and disables the button while an action is in progress. */
  busy?: boolean;
  busyLabel?: string;
}

export function Button({
  variant = "primary",
  size = "md",
  busy = false,
  busyLabel = "Please wait…",
  type = "button",
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-sm border font-semibold",
        "disabled:cursor-not-allowed disabled:opacity-60",
        size === "sm" ? "min-h-8 px-3 text-sm" : "min-h-10 px-4 text-base",
        variants[variant],
        className,
      )}
      {...rest}
    >
      {busy ? busyLabel : children}
    </button>
  );
}
