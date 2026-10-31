import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router";

import { apiSend, getJson } from "@/lib/api/client";

export function useApi<T>(path: string | null, params?: Record<string, unknown>, options: { refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: [path, params ?? {}] as QueryKey,
    queryFn: ({ signal }) => getJson<T>(path as string, params, signal),
    enabled: path !== null,
    refetchInterval: options.refetchInterval,
  });
}

export function useApiMutation<TBody, TResult = unknown>(
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  path: string | ((body: TBody) => string),
  invalidate: string[] = [],
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) => apiSend<TResult>(method, typeof path === "function" ? path(body) : path, body),
    onSuccess: () =>
      Promise.all(
        invalidate.map((prefix) =>
          qc.invalidateQueries({ predicate: (q) => typeof q.queryKey[0] === "string" && (q.queryKey[0] as string).startsWith(prefix) }),
        ),
      ),
  });
}

/** Filters kept in the URL so every view (and every dashboard KPI link) is shareable. */
export function useUrlFilters<T extends Record<string, string | string[] | undefined>>(keys: (keyof T)[], multi: (keyof T)[] = []) {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => {
    const out: Record<string, string | string[] | undefined> = {};
    for (const k of keys) {
      const key = String(k);
      out[key] = multi.includes(k) ? params.getAll(key) : (params.get(key) ?? undefined);
    }
    return out as T;
  }, [params, keys, multi]);
  const setFilters = useCallback(
    (next: Partial<T>) => {
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries({ ...filters, ...next })) {
        if (Array.isArray(v)) v.forEach((x) => x && p.append(k, x));
        else if (v) p.set(k, v);
      }
      setParams(p);
    },
    [filters, setParams],
  );
  return [filters, setFilters] as const;
}
