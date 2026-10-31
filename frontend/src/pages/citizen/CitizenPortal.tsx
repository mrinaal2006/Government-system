/**
 * Citizen self-service portal: register with a mobile number, verify it with a one-time
 * code, sign in, file grievances and track them. Separate session from officers.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams, useSearchParams } from "react-router";

import { Alert, Button, Checkbox, EmptyState, ErrorState, LoadingState, PageHeader, SelectField, StatusBadge, TextAreaField, TextField } from "@/design-system";
import { Footer } from "@/layout/Footer";
import { GovHeader } from "@/layout/GovHeader";
import { MAIN_CONTENT_ID, SkipLink } from "@/layout/SkipLink";
import { ApiError, apiGet, apiSend, errorMessage, fieldErrors } from "@/lib/api/client";
import { formatDateTimeIST, formatShortIST, STATUS_TONE } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { LocationPicker, type LocationValue } from "@/lib/LocationPicker";
import { options } from "@/lib/reference";

interface Citizen { id: string; name: string | null; mobile: string | null; verified: boolean }
interface MyGrievance { id: string; reference_no: string; subject: string; status: string; status_label: string; registered_at: string; updated_at: string }
interface GrievanceDetail extends MyGrievance { description: string; responsible_office: string | null; resolution: string | null; timeline: Array<{ status_label: string; at: string }> }
interface CodeResponse { message: string; development_otp?: string }

const ME_KEY = ["citizen-me"];

function useCitizen() {
  return useQuery({
    queryKey: ME_KEY,
    queryFn: async () => {
      try {
        return (await apiGet<Citizen>("/citizen/me")).data;
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null;
        throw e;
      }
    },
    retry: false,
  });
}

export function CitizenLayout() {
  const me = useCitizen();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const signOut = async () => {
    await apiSend("POST", "/citizen/logout").catch(() => undefined);
    qc.setQueryData(ME_KEY, null);
    navigate("/citizen", { replace: true });
  };
  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <GovHeader />
      <nav aria-label="Citizen portal" className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-4xl flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
          <span className="font-semibold text-brand">Citizen grievance portal</span>
          {me.data ? (
            <span className="flex flex-wrap items-center gap-3">
              <Link to="/citizen" className="text-link underline">My grievances</Link>
              <Link to="/citizen/new" className="text-link underline">File a grievance</Link>
              <span className="text-ink-muted">{me.data.name}</span>
              <Button size="sm" variant="secondary" onClick={() => void signOut()}>Sign out</Button>
            </span>
          ) : null}
        </div>
      </nav>
      <main id={MAIN_CONTENT_ID} tabIndex={-1} className="mx-auto w-full max-w-4xl flex-1 px-4 py-8 focus:outline-none">
        {me.isLoading ? <LoadingState /> : me.isError ? <ErrorState message={errorMessage(me.error)} onRetry={() => void me.refetch()} /> : <Outlet />}
      </main>
      <Footer />
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mx-auto max-w-md rounded-sm border border-line bg-surface p-6">
      <h1 className="m-0 mb-4 text-xl font-semibold text-brand">{title}</h1>
      {children}
    </div>
  );
}

function RequireCitizen({ children }: { children: ReactNode }) {
  const me = useCitizen();
  const loc = useLocation();
  if (me.isLoading) return <LoadingState />;
  if (!me.data) return <Navigate to={`/citizen/login?next=${encodeURIComponent(loc.pathname)}`} replace />;
  return <>{children}</>;
}

function safeNext(raw: string | null): string {
  return raw && raw.startsWith("/citizen") && !raw.startsWith("//") ? raw : "/citizen";
}

function DevCode({ code }: { code?: string }) {
  if (!code) return null;
  return (
    <Alert tone="warning" title={`Development only: your code is ${code}`} className="mb-4">
      No SMS provider is configured, so the code is shown here. This never happens in production, which refuses to enable the
      portal without a real SMS provider.
    </Alert>
  );
}

// --- Home ---------------------------------------------------------------------------------------

export function CitizenHomePage() {
  const me = useCitizen();
  if (me.data) return <MyGrievancesPage />;
  return (
    <>
      <PageHeader title="Citizen grievance portal" description="File a grievance with the district administration and track what is being done about it." />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-sm border border-line bg-surface p-5">
          <h2 className="mt-0 text-lg">New here?</h2>
          <p>Create an account with your mobile number. We send a one-time code to confirm the number is yours.</p>
          <Link to="/citizen/register" className="text-link underline">Create an account</Link>
        </div>
        <div className="rounded-sm border border-line bg-surface p-5">
          <h2 className="mt-0 text-lg">Already registered?</h2>
          <p>Sign in with your mobile number and password to file a grievance or see the status of yours.</p>
          <Link to="/citizen/login" className="text-link underline">Sign in</Link>
        </div>
      </div>
      <p className="mt-6 text-sm text-ink-muted">
        Government officials sign in <Link to="/login" className="text-link underline">here</Link>.
      </p>
    </>
  );
}

// --- Register / verify / sign in -----------------------------------------------------------------

export function CitizenRegisterPage() {
  const navigate = useNavigate();
  const cfg = useApi<{ consent_version: string }>("/citizen/config");
  const [f, setF] = useState({ mobile: "", name: "", email: "", password: "", confirm: "", consent: false });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const local: Record<string, string> = {};
    if (f.password !== f.confirm) local.confirm = "The passwords do not match.";
    if (!f.consent) local.consent = "Please accept to continue.";
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      const r = await apiSend<CodeResponse>("POST", "/citizen/register", {
        mobile: f.mobile, name: f.name.trim(), email: f.email.trim() || null, password: f.password, consent: f.consent,
      });
      navigate("/citizen/verify", { state: { mobile: f.mobile, code: r.development_otp } });
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Create an account">
      {error ? <Alert tone="danger" title={error} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Mobile number" required type="tel" inputMode="numeric" autoComplete="tel-national" hint="10-digit Indian mobile number."
          value={f.mobile} onChange={(e) => setF({ ...f, mobile: e.target.value })} error={errors.mobile} />
        <TextField label="Your name" required autoComplete="name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} error={errors.name} />
        <TextField label="Email (optional)" type="email" autoComplete="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} error={errors.email} />
        <TextField label="Password" required type="password" autoComplete="new-password" hint="At least 12 characters with three character types; must not contain your name or mobile number."
          value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} error={errors.password} />
        <TextField label="Confirm password" required type="password" autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} error={errors.confirm} />
        <div className="mb-4 rounded-sm border border-line bg-surface-muted p-3 text-sm">
          <p className="mt-0">
            Your name, mobile number and email are stored encrypted and used only to process your grievances and contact you
            about them. Officers handling your grievance can see your contact details. Notice version {cfg.data?.consent_version ?? "-"}.
          </p>
          <Checkbox label="I agree to my details being used to process my grievances" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} />
          {errors.consent ? <p className="m-0 text-danger">{errors.consent}</p> : null}
        </div>
        <Button type="submit" busy={busy} busyLabel="Creating account…" className="w-full">Create account</Button>
      </form>
      <p className="mt-4 text-sm">Already registered? <Link to="/citizen/login" className="text-link underline">Sign in</Link></p>
    </Card>
  );
}

export function CitizenVerifyPage() {
  const loc = useLocation();
  const navigate = useNavigate();
  const initial = (loc.state ?? {}) as { mobile?: string; code?: string };
  const [mobile, setMobile] = useState(initial.mobile ?? "");
  const [code, setCode] = useState("");
  const [devCode, setDevCode] = useState(initial.code);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await apiSend("POST", "/citizen/verify", { mobile, code });
      navigate("/citizen/login?verified=1", { replace: true, state: { mobile } });
    } catch (err) {
      setError(errorMessage(err));
      setCode("");
    } finally {
      setBusy(false);
    }
  };
  const resend = async () => {
    setError(null);
    try {
      const r = await apiSend<CodeResponse>("POST", "/citizen/otp/resend", { mobile });
      setInfo(r.message);
      setDevCode(r.development_otp);
    } catch (err) {
      setError(errorMessage(err));
    }
  };
  return (
    <Card title="Verify your mobile number">
      <DevCode code={devCode} />
      {info ? <Alert tone="info" title={info} className="mb-4" live /> : null}
      {error ? <Alert tone="danger" title={error} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Mobile number" required type="tel" inputMode="numeric" value={mobile} onChange={(e) => setMobile(e.target.value)} />
        <TextField label="6-digit code" required inputMode="numeric" autoComplete="one-time-code" maxLength={6} hint="The code is valid for 10 minutes."
          value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} />
        <Button type="submit" busy={busy} busyLabel="Verifying…" className="w-full" disabled={code.length !== 6}>Verify</Button>
      </form>
      <p className="mt-4 text-sm">
        Did not get a code? <button type="button" className="text-link underline" disabled={!mobile} onClick={() => void resend()}>Send a new code</button>
      </p>
    </Card>
  );
}

export function CitizenLoginPage() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const loc = useLocation();
  const [params] = useSearchParams();
  const me = useCitizen();
  const [mobile, setMobile] = useState(((loc.state ?? {}) as { mobile?: string }).mobile ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<{ text: string; unverified: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const next = safeNext(params.get("next"));
  if (me.data) return <Navigate to={next} replace />;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const c = await apiSend<Citizen>("POST", "/citizen/login", { mobile, password });
      qc.setQueryData(ME_KEY, c);
      setPassword("");
      navigate(next, { replace: true });
    } catch (err) {
      setError({ text: errorMessage(err), unverified: err instanceof ApiError && err.code === "mobile_not_verified" });
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Sign in">
      {params.get("verified") ? <Alert tone="success" title="Your mobile number is verified. Sign in to continue." className="mb-4" /> : null}
      {error ? (
        <Alert tone="danger" title={error.text} className="mb-4">
          {error.unverified ? <Link to="/citizen/verify" state={{ mobile }} className="text-link underline">Verify now</Link> : null}
        </Alert>
      ) : null}
      <form onSubmit={submit} noValidate>
        <TextField label="Mobile number" required type="tel" inputMode="numeric" autoComplete="tel-national" value={mobile} onChange={(e) => setMobile(e.target.value)} />
        <TextField label="Password" required type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" busy={busy} busyLabel="Signing in…" className="w-full" disabled={!mobile || !password}>Sign in</Button>
      </form>
      <p className="mt-4 text-sm">New here? <Link to="/citizen/register" className="text-link underline">Create an account</Link></p>
    </Card>
  );
}

// --- Grievances ----------------------------------------------------------------------------------

function MyGrievancesPage() {
  const list = useApi<MyGrievance[]>("/citizen/grievances");
  return (
    <>
      <PageHeader title="My grievances" actions={<Link to="/citizen/new" className="font-semibold text-link underline">File a grievance</Link>} />
      {list.isLoading ? <LoadingState /> : list.isError ? <ErrorState message={errorMessage(list.error)} onRetry={() => void list.refetch()} />
        : !list.data?.length ? <EmptyState title="You have not filed any grievances yet." action={<Link to="/citizen/new" className="text-link underline">File a grievance</Link>} />
        : (
          <ul className="m-0 list-none p-0">
            {list.data.map((g) => (
              <li key={g.id} className="mb-3 rounded-sm border border-line bg-surface p-4">
                <Link to={`/citizen/grievances/${g.id}`} className="font-semibold text-link underline">{g.subject}</Link>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-ink-muted">
                  <span>{g.reference_no}</span>
                  <StatusBadge tone={STATUS_TONE[g.status] ?? "neutral"}>{g.status_label}</StatusBadge>
                  <span>Filed {formatShortIST(g.registered_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        )}
    </>
  );
}

export function CitizenNewGrievancePage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const cats = useApi<Array<{ id: string; name_en: string }>>("/citizen/reference/categories");
  const [f, setF] = useState({ subject: "", description: "", category_id: "", location_text: "", address: "" });
  const [location, setLocation] = useState<LocationValue>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await apiSend<{ id: string; reference_no: string }>("POST", "/citizen/grievances", {
        subject: f.subject.trim(), description: f.description.trim(), category_id: f.category_id || null, location,
        location_text: f.location_text.trim() || null, address: f.address.trim() || null,
      });
      await qc.invalidateQueries({ queryKey: ["/citizen/grievances"] });
      navigate(`/citizen/grievances/${r.id}`, { state: { filed: r.reference_no } });
    } catch (err) {
      setErrors(fieldErrors(err));
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <RequireCitizen>
      <PageHeader title="File a grievance" description="Describe the problem and where it is. You will get a reference number to track it." />
      {error ? <Alert tone="danger" title={error} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate className="max-w-2xl">
        <TextField label="Subject" required maxLength={300} value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} error={errors.subject} />
        <TextAreaField label="Description" required rows={6} maxLength={10000} hint="What is the problem, since when, and who is affected? At least 20 characters."
          value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} error={errors.description} />
        <SelectField label="Type of problem" placeholder="Not sure" options={options(cats.data)} value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })} />
        <LocationPicker value={location} onChange={setLocation} errors={errors} referenceBase="/citizen/reference" />
        <TextField label="Landmark or exact place (optional)" maxLength={500} value={f.location_text} onChange={(e) => setF({ ...f, location_text: e.target.value })} />
        <TextField label="Your address (optional)" maxLength={500} autoComplete="street-address" value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} />
        <Button type="submit" busy={busy} busyLabel="Submitting…">Submit grievance</Button>
      </form>
    </RequireCitizen>
  );
}

export function CitizenGrievanceDetailPage() {
  const { id } = useParams();
  const loc = useLocation();
  const filed = ((loc.state ?? {}) as { filed?: string }).filed;
  const g = useApi<GrievanceDetail>(id ? `/citizen/grievances/${id}` : null);
  return (
    <RequireCitizen>
      {filed ? <Alert tone="success" title={`Grievance filed. Your reference number is ${filed}.`} className="mb-4" live /> : null}
      {g.isLoading ? <LoadingState /> : g.isError || !g.data ? <ErrorState message={errorMessage(g.error)} /> : (
        <>
          <PageHeader title={g.data.subject} description={g.data.reference_no} />
          <p><StatusBadge tone={STATUS_TONE[g.data.status] ?? "neutral"}>{g.data.status_label}</StatusBadge></p>
          <dl className="grid grid-cols-1 gap-x-6 md:grid-cols-[max-content_1fr]">
            <dt className="font-semibold">Filed</dt><dd className="m-0 mb-2">{formatDateTimeIST(g.data.registered_at)}</dd>
            <dt className="font-semibold">Responsible office</dt><dd className="m-0 mb-2">{g.data.responsible_office ?? "Being decided"}</dd>
            <dt className="font-semibold">Your description</dt><dd className="m-0 mb-2 whitespace-pre-wrap">{g.data.description}</dd>
            {g.data.resolution ? <><dt className="font-semibold">Action taken</dt><dd className="m-0 mb-2 whitespace-pre-wrap">{g.data.resolution}</dd></> : null}
          </dl>
          <h2 className="text-lg">Progress</h2>
          <ol className="pl-5">
            {g.data.timeline.map((t, i) => <li key={i}>{t.status_label}, {formatDateTimeIST(t.at)}</li>)}
          </ol>
          <p><Link to="/citizen" className="text-link underline">Back to my grievances</Link></p>
        </>
      )}
    </RequireCitizen>
  );
}
