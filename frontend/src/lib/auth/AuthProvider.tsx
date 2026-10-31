import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";

import { ApiError, apiGet, apiSend, onAuthError } from "@/lib/api/client";

export type AuthState = "anonymous" | "authenticated" | "mfa_required" | "mfa_enrollment_required" | "password_change_required";

export interface SessionUser {
  id: string;
  username: string;
  full_name: string;
  roles: string[];
  permissions: string[];
  mfa_enrolled: boolean;
}

export interface SessionInfo {
  state: Exclude<AuthState, "anonymous">;
  user: SessionUser;
}

interface AuthContextValue {
  state: AuthState | "loading";
  user: SessionUser | null;
  /** Presentation only: the server enforces every permission independently. */
  can: (...permissions: string[]) => boolean;
  setSession: (info: SessionInfo) => void;
  logout: () => Promise<void>;
  refresh: () => Promise<unknown>;
}

const AuthContext = createContext<AuthContextValue | null>(null);
export const ME_KEY = ["auth", "me"] as const;

async function fetchMe(): Promise<SessionInfo | null> {
  try {
    return (await apiGet<SessionInfo>("/auth/me")).data;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ME_KEY, queryFn: fetchMe, staleTime: 60_000, retry: false });

  useEffect(() => onAuthError(() => void qc.invalidateQueries({ queryKey: ME_KEY })), [qc]);

  const setSession = useCallback((info: SessionInfo) => qc.setQueryData(ME_KEY, info), [qc]);
  const logout = useCallback(async () => {
    try {
      await apiSend("POST", "/auth/logout");
    } finally {
      // Mark the session anonymous first, then drop every other cached response so no
      // data from the previous session remains in memory.
      qc.setQueryData(ME_KEY, null);
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== ME_KEY[0] });
    }
  }, [qc]);

  const value = useMemo<AuthContextValue>(() => {
    const info = me.data;
    const permissions = new Set(info?.user.permissions ?? []);
    return {
      state: me.isPending ? "loading" : info ? info.state : "anonymous",
      user: info?.user ?? null,
      can: (...perms) => perms.every((p) => permissions.has(p)),
      setSession,
      logout,
      refresh: () => me.refetch(),
    };
  }, [me, setSession, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
