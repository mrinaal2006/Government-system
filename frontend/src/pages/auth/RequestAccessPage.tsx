import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Alert, Button, LoadingState, SelectField, TextAreaField, TextField } from "@/design-system";
import { apiSend, errorMessage, fieldErrors } from "@/lib/api/client";
import { useApi } from "@/lib/hooks";

import { AuthLayout } from "./AuthLayout";

export interface SignupOptions {
  officer_signup_enabled: boolean;
  citizen_portal_enabled: boolean;
  roles: Array<{ code: string; name: string }>;
  departments: Array<{ id: string; name: string }>;
}

const EMPTY = { username: "", full_name: "", designation: "", email: "", department_id: "", requested_role: "", note: "", password: "", confirm: "" };

/** Officials ask for an account. Nothing is granted until an administrator approves it. */
export function RequestAccessPage() {
  const opts = useApi<SignupOptions>("/auth/signup/options");
  const [f, setF] = useState(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const set = (k: keyof typeof EMPTY) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value });

  if (opts.isLoading) return <AuthLayout title="Request access"><LoadingState /></AuthLayout>;
  if (!opts.data?.officer_signup_enabled) {
    return (
      <AuthLayout title="Request access">
        <Alert tone="info" title="Access requests are not accepted online. Contact the district administration." />
        <p className="mt-4"><Link to="/login" className="text-link underline">Back to sign in</Link></p>
      </AuthLayout>
    );
  }
  if (done) {
    return (
      <AuthLayout title="Request submitted">
        <Alert tone="success" title="Your request has been sent to the district administrators." live />
        <p>
          You cannot sign in until an administrator approves it and assigns your role and area of responsibility.
          If you sign in before then, you will be told that the request is still pending.
        </p>
        <p className="mt-4"><Link to="/login" className="text-link underline">Back to sign in</Link></p>
      </AuthLayout>
    );
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const local: Record<string, string> = {};
    if (!f.requested_role) local.requested_role = "Choose the role you need.";
    if (f.password !== f.confirm) local.confirm = "The passwords do not match.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      await apiSend("POST", "/auth/signup", {
        username: f.username.trim(),
        full_name: f.full_name.trim(),
        designation: f.designation.trim(),
        email: f.email.trim(),
        department_id: f.department_id || null,
        requested_role: f.requested_role,
        note: f.note.trim() || null,
        password: f.password,
      });
      setDone(true);
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout title="Request access" notice="Requests are reviewed by the district administration. All activity is recorded.">
      <p className="mt-0 text-sm text-ink-muted">
        For government officials. Citizens should use the <Link to="/citizen" className="text-link underline">citizen portal</Link>.
      </p>
      {error ? <Alert tone="danger" title={error} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Username" required autoComplete="username" hint="Lower case letters, digits, dots and hyphens; 3-64 characters."
          value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} error={errors.username} />
        <TextField label="Full name" required autoComplete="name" value={f.full_name} onChange={set("full_name")} error={errors.full_name} />
        <TextField label="Designation" required autoComplete="organization-title" value={f.designation} onChange={set("designation")} error={errors.designation} />
        <TextField label="Official email" type="email" required autoComplete="email" value={f.email} onChange={set("email")} error={errors.email} />
        <SelectField label="Department" placeholder="Not applicable" options={opts.data.departments.map((d) => ({ value: d.id, label: d.name }))}
          value={f.department_id} onChange={set("department_id")} />
        <SelectField label="Role requested" required placeholder="Select" options={opts.data.roles.map((r) => ({ value: r.code, label: r.name }))}
          value={f.requested_role} onChange={set("requested_role")} error={errors.requested_role}
          hint="The administrator decides the final role and area of responsibility." />
        <TextAreaField label="Reason or office order reference" value={f.note} onChange={set("note")} maxLength={1000} error={errors.note} />
        <TextField label="Password" type="password" required autoComplete="new-password" value={f.password} onChange={set("password")} error={errors.password}
          hint="At least 12 characters with three character types; must not contain your name or username." />
        <TextField label="Confirm password" type="password" required autoComplete="new-password" value={f.confirm} onChange={set("confirm")} error={errors.confirm} />
        <Button type="submit" busy={busy} busyLabel="Submitting…" className="w-full">Submit request</Button>
      </form>
      <p className="mt-4 text-sm"><Link to="/login" className="text-link underline">Back to sign in</Link></p>
    </AuthLayout>
  );
}
