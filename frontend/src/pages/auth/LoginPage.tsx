import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router";

import { Alert, Button, TextField } from "@/design-system";
import { apiSend, errorMessage } from "@/lib/api/client";
import { useAuth, type SessionInfo } from "@/lib/auth/AuthProvider";
import { useApi } from "@/lib/hooks";

import type { SignupOptions } from "./SignUpPage";

import { AuthLayout } from "./AuthLayout";
import { pathForState, safeReturnPath } from "./authFlow";

export function LoginPage() {
  const { state, setSession } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const next = safeReturnPath(params.get("next"));
  const signup = useApi<SignupOptions>("/auth/signup/options");

  if (state === "authenticated") return <Navigate to={next} replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    try {
      const info = await apiSend<SessionInfo>("POST", "/auth/login", { username: username.trim(), password });
      setSession(info);
      setPassword("");
      navigate(info.state === "authenticated" ? next : `${pathForState(info.state)}?next=${encodeURIComponent(next)}`, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Sign in">
      {params.get("expired") ? <Alert tone="warning" title="Your session ended. Please sign in again." className="mb-4" /> : null}
      {error ? <Alert tone="danger" title={error} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Username" name="username" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
        <TextField label="Password" name="password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <Button type="submit" busy={busy} busyLabel="Signing in…" className="w-full">
          Sign in
        </Button>
      </form>
      {/* Shown unless the server explicitly turns them off, so a slow or failing options call never hides sign-up. */}
      <div className="mt-6 border-t border-line pt-4 text-sm">
        {signup.data?.officer_signup_enabled !== false ? (
          <p className="m-0 mb-2">
            Don&apos;t have an account? <Link to="/signup" className="text-link underline">Sign up</Link>
          </p>
        ) : null}
        {signup.data?.citizen_portal_enabled ? (
          <p className="m-0">
            Citizen? <Link to="/citizen" className="text-link underline">File or track a grievance on the citizen portal</Link>
          </p>
        ) : null}
      </div>
    </AuthLayout>
  );
}
