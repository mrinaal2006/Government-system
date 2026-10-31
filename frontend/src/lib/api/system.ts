import { useQuery } from "@tanstack/react-query";

import { apiGet } from "./client";

export type ComponentState = "ok" | "unavailable";

export interface ComponentStatus {
  status: ComponentState;
  latency_ms: number;
  reason: string | null;
}

export interface Readiness {
  status: ComponentState;
  checked_at: string;
  components: Record<string, ComponentStatus>;
}

export interface SystemInfo {
  application: string;
  version: string;
  environment: "development" | "test" | "staging" | "production";
  deployment: {
    district_name: string | null;
    district_name_local: string | null;
    state_name: string | null;
    state_name_local: string | null;
  };
}

export function useSystemInfo() {
  return useQuery({
    queryKey: ["system", "info"],
    queryFn: async ({ signal }) => (await apiGet<SystemInfo>("/system/info", { signal })).data,
    staleTime: 5 * 60_000,
  });
}

export function useReadiness() {
  return useQuery({
    queryKey: ["system", "readiness"],
    // 503 carries a valid readiness body describing which component is down.
    queryFn: async ({ signal }) => (await apiGet<Readiness>("/health/ready", { signal, acceptStatuses: [503] })).data,
    refetchInterval: 30_000,
  });
}
