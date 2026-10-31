import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { AccessibilityPreferencesProvider } from "@/lib/a11y/preferences";
import { ApiError } from "@/lib/api/client";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        // Retry transient failures only; never retry authorisation or validation errors.
        retry: (count, error) => count < 2 && (!(error instanceof ApiError) || error.status === 0 || error.status >= 500),
      },
    },
  });
}

export function AppProviders({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <AccessibilityPreferencesProvider>{children}</AccessibilityPreferencesProvider>
    </QueryClientProvider>
  );
}
