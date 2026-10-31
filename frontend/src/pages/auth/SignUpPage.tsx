import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router";

import { Alert, Button, LoadingState, TextField } from "@/design-system";
import { apiSend, errorMessage, fieldErrors } from "@/lib/api/client";
import { useAuth, type SessionInfo } from "@/lib/auth/AuthProvider";
import { useApi } from "@/lib/hooks";

import { AuthLayout } from "./AuthLayout";
import { pathForState } from "./authFlow";

export interface SignupOptions {
  officer_signup_enabled: boolean;
  citizen_portal_enabled: boolean;
}

const EMPTY = { username: "", full_name: "", email: "", password: "", confirm: "" };

/** Create an account and sign straight in. No approval step. */
export function SignUpPage() {
  const { state, setSession } = useAuth();
  const navigate = useNavigate();
  const opts = useApi<SignupOptions>("/auth/signup/options");
  const [f, setF] = useState(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  if (state === "authenticated") return <Navigate to="/" replace />;
  if (opts.isLoading) return <AuthLayout title="Sign up"><LoadingState /></AuthLayout>;
  if (opts.data?.officer_signup_enabled === false) {
    return (
      <AuthLayout title="Sign up">
        <Alert tone="info" title="Sign-up is turned off. Contact the district administration for an account." />
        <p className="mt-4"><Link to="/login" className="text-link underline">Back to sign in</Link></p>
      </AuthLayout>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const local: Record<string, string> = {};
    if (!f.username.trim()) local.username = "Choose a username.";
    if (!f.full_name.trim()) local.full_name = "Enter your name.";
    if (!f.password) local.password = "Choose a password.";
    else if (f.password !== f.confirm) local.confirm = "The passwords do not match.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      const info = await apiSend<SessionInfo>("POST", "/auth/signup", {
        username: f.username.trim(),
        full_name: f.full_name.trim(),
        email: f.email.trim() || null,
        password: f.password,
      });
      setSession(info);
      navigate(pathForState(info.state) ?? "/", { replace: true });
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Sign up" notice="All activity is recorded.">
      {error ? <Alert tone="danger" title={error} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Username" required autoComplete="username" hint="Lower case letters, digits, dots and hyphens; 3-64 characters."
          value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} error={errors.username} />
        <TextField label="Full name" required autoComplete="name" value={f.full_name} onChange={set("full_name")} error={errors.full_name} />
        <TextField label="Email (optional)" type="email" autoComplete="email" value={f.email} onChange={set("email")} error={errors.email} />
        <TextField label="Password" type="password" required autoComplete="new-password" value={f.password} onChange={set("password")} error={errors.password}
          hint="At least 12 characters with three of: lower case, upper case, digits, symbols. Must not contain your name or username." />
        <TextField label="Confirm password" type="password" required autoComplete="new-password" value={f.confirm} onChange={set("confirm")} error={errors.confirm} />
        <Button type="submit" busy={busy} busyLabel="Creating account…" className="w-full">Sign up</Button>
      </form>
      <p className="mt-4 text-sm">Already have an account? <Link to="/login" className="text-link underline">Sign in</Link></p>
    </AuthLayout>
  );
}
