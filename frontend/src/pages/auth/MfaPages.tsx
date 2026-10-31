import QRCode from "qrcode";
import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate, useSearchParams } from "react-router";

import { Alert, Button, TextField } from "@/design-system";
import { apiSend, errorMessage } from "@/lib/api/client";
import { useAuth, type SessionInfo } from "@/lib/auth/AuthProvider";

import { AuthLayout } from "./AuthLayout";
import { pathForState, safeReturnPath } from "./authFlow";

function useAfterStep() {
  const { setSession } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = safeReturnPath(params.get("next"));
  return (info: SessionInfo) => {
    setSession(info);
    navigate(info.state === "authenticated" ? next : `${pathForState(info.state)}?next=${encodeURIComponent(next)}`, { replace: true });
  };
}

function CodeForm({ endpoint, label }: { endpoint: string; label: string }) {
  const after = useAfterStep();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!/^\d{6}$/.test(code)) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      after(await apiSend<SessionInfo>("POST", endpoint, { code }));
    } catch (err) {
      setError(errorMessage(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} noValidate>
      <TextField label={label} name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code}
        onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} error={error ?? undefined} required />
      <Button type="submit" busy={busy} busyLabel="Verifying…" className="w-full">Verify</Button>
    </form>
  );
}

function useNextPath(): string {
  const [params] = useSearchParams();
  return safeReturnPath(params.get("next"));
}

export function MfaVerifyPage() {
  const { state } = useAuth();
  const next = useNextPath();
  if (state !== "mfa_required" && state !== "loading") return <Navigate to={pathForState(state) ?? next} replace />;
  return (
    <AuthLayout title="Verify your identity">
      <p className="mt-0 text-ink-muted">Open your authenticator app and enter the current 6-digit code.</p>
      <CodeForm endpoint="/auth/mfa/verify" label="Verification code" />
    </AuthLayout>
  );
}

export function MfaSetupPage() {
  const { state } = useAuth();
  const next = useNextPath();
  const [setup, setSetup] = useState<{ secret: string; otpauth_uri: string } | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (state !== "mfa_enrollment_required" || setup) return;
    apiSend<{ secret: string; otpauth_uri: string }>("POST", "/auth/mfa/setup")
      .then(async (s) => {
        setSetup(s);
        setQr(await QRCode.toDataURL(s.otpauth_uri, { margin: 1, width: 220 }));
      })
      .catch((err) => setError(errorMessage(err)));
  }, [state, setup]);

  if (state !== "mfa_enrollment_required" && state !== "loading") return <Navigate to={pathForState(state) ?? next} replace />;
  return (
    <AuthLayout title="Set up multi-factor authentication">
      <p className="mt-0 text-ink-muted">
        Your role requires a second factor. Scan the code with an authenticator app (for example any TOTP app approved by your
        department), then enter the 6-digit code it shows.
      </p>
      {error ? <Alert tone="danger" title={error} className="mb-3" /> : null}
      {setup ? (
        <>
          {qr ? <img src={qr} alt="QR code for adding this account to an authenticator app" width={220} height={220} className="mx-auto block" /> : null}
          <p className="text-sm">
            If you cannot scan, enter this key manually:{" "}
            <code className="break-all rounded-sm bg-surface-muted px-1">{setup.secret}</code>
          </p>
          <CodeForm endpoint="/auth/mfa/confirm" label="Code from your authenticator app" />
        </>
      ) : !error ? (
        <p role="status">Preparing…</p>
      ) : null}
    </AuthLayout>
  );
}

export function ChangePasswordPage() {
  const { state, user } = useAuth();
  const after = useAfterStep();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (state === "anonymous") return <Navigate to="/login" replace />;
  const forced = state === "password_change_required";
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (form.next !== form.confirm) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      after(await apiSend<SessionInfo>("POST", "/auth/password", { current_password: form.current, new_password: form.next }));
      setForm({ current: "", next: "", confirm: "" });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthLayout title={forced ? "Change your temporary password" : "Change password"}>
      {forced ? <Alert tone="info" title={`Welcome, ${user?.full_name ?? ""}. Choose a new password to continue.`} className="mb-3" /> : null}
      {error ? <Alert tone="danger" title={error} className="mb-3" /> : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Current password" type="password" autoComplete="current-password" value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} required />
        <TextField label="New password" type="password" autoComplete="new-password" hint="At least 12 characters using three of: lower case, upper case, digits, symbols. Must not contain your username."
          value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} required />
        <TextField label="Confirm new password" type="password" autoComplete="new-password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} required />
        <Button type="submit" busy={busy} className="w-full">Change password</Button>
      </form>
    </AuthLayout>
  );
}
