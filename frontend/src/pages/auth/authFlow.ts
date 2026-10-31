import type { AuthState } from "@/lib/auth/AuthProvider";

export function pathForState(state: AuthState | "loading"): string | null {
  switch (state) {
    case "mfa_required":
      return "/login/verify";
    case "mfa_enrollment_required":
      return "/login/setup-mfa";
    case "password_change_required":
      return "/login/change-password";
    case "anonymous":
      return "/login";
    default:
      return null;
  }
}

/** Only allow in-app relative return paths (no open redirects). */
export function safeReturnPath(value: string | null): string {
  return value && value.startsWith("/") && !value.startsWith("//") && !value.startsWith("/login") ? value : "/";
}
