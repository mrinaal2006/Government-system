import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { EmptyState, LoadingState, PageHeader } from "@/design-system";
import { useAuth } from "@/lib/auth/AuthProvider";
import { pathForState } from "@/pages/auth/authFlow";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { state } = useAuth();
  const location = useLocation();
  if (state === "loading") return <LoadingState label="Checking your session…" />;
  if (state !== "authenticated") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`${pathForState(state)}?next=${next}`} replace />;
  }
  return <>{children}</>;
}

/** Hides screens the user lacks permission for. Presentation only; the API enforces access. */
export function RequirePermission({ all, children }: { all: string[]; children: ReactNode }) {
  const { can } = useAuth();
  if (!can(...all)) {
    return (
      <>
        <PageHeader title="Access not permitted" />
        <EmptyState title="Your role does not include access to this section">
          If you need access, ask the system administrator to review your role and area of responsibility.
        </EmptyState>
      </>
    );
  }
  return <>{children}</>;
}
