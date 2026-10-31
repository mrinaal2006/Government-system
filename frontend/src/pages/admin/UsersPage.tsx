import { useState, type FormEvent } from "react";

import { Alert, Button, Checkbox, DataTable, Dialog, PageHeader, Pagination, SelectField, StatusBadge, TextField } from "@/design-system";
import { apiSend, errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthProvider";
import { formatShortIST, titleCase } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { options, useDepartments, useUnits } from "@/lib/reference";

interface Scope { scope_type: string; district_id?: string | null; subdivision_id?: string | null; block_id?: string | null; department_id?: string | null }
interface UserRow { id: string; username: string; full_name: string; designation: string | null; email: string | null; department_id: string | null; is_active: boolean; locked: boolean; must_change_password: boolean; mfa_enrolled: boolean; last_login_at: string | null; roles: string[]; scopes: Scope[] }
interface Role { code: string; name: string; permissions: string[] }

export function UsersPage() {
  const { can, user: me } = useAuth();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const users = useApi<{ items: UserRow[]; total: number }>("/iam/users", { q: q || undefined, limit: 25, offset });
  const roles = useApi<Role[]>("/iam/roles");
  const [editing, setEditing] = useState<UserRow | "new" | null>(null);
  const [msg, setMsg] = useState<{ tone: "success" | "danger"; text: string } | null>(null);
  const manage = can("iam.users.manage");
  const act = (path: string, body: unknown, text: string) =>
    apiSend("POST", path, body).then(() => { setMsg({ tone: "success", text }); void users.refetch(); }, (e) => setMsg({ tone: "danger", text: errorMessage(e) }));
  return (
    <>
      <PageHeader title="Users and roles" description="Accounts, roles and areas of responsibility. Every change is audited."
        actions={manage ? <Button onClick={() => setEditing("new")}>Create user</Button> : null} />
      {msg ? <Alert tone={msg.tone} title={msg.text} live className="mb-4" /> : null}
      <div className="max-w-md"><TextField label="Search by username or name" value={q} onChange={(e) => { setQ(e.target.value); setOffset(0); }} /></div>
      <DataTable<UserRow> caption="User accounts" rows={users.data?.items} rowKey={(u) => u.id} loading={users.isLoading}
        columns={[
          { key: "u", header: "User", render: (u) => <><strong>{u.full_name}</strong><br /><span className="text-sm text-ink-muted">{u.username}</span></> },
          { key: "r", header: "Roles", render: (u) => u.roles.map(titleCase).join(", ") || "-" },
          { key: "s", header: "Area", render: (u) => u.scopes.map((s) => titleCase(s.scope_type)).join(", ") || "None" },
          { key: "st", header: "Status", render: (u) => <span className="flex flex-wrap gap-1">
            <StatusBadge tone={u.is_active ? "success" : "neutral"}>{u.is_active ? "Active" : "Inactive"}</StatusBadge>
            {u.locked ? <StatusBadge tone="danger">Locked</StatusBadge> : null}
            <StatusBadge tone={u.mfa_enrolled ? "success" : "warning"}>{u.mfa_enrolled ? "MFA" : "No MFA"}</StatusBadge></span> },
          { key: "l", header: "Last sign-in", render: (u) => formatShortIST(u.last_login_at) },
          { key: "a", header: "Actions", render: (u) => manage ? (
            <span className="flex flex-wrap gap-1">
              <Button size="sm" variant="secondary" onClick={() => setEditing(u)}>Edit</Button>
              {u.locked ? <Button size="sm" variant="secondary" onClick={() => void act(`/iam/users/${u.id}/unlock`, {}, "Account unlocked.")}>Unlock</Button> : null}
              {u.mfa_enrolled && u.id !== me?.id ? <Button size="sm" variant="secondary" onClick={() => void act(`/iam/users/${u.id}/mfa/reset`, {}, "MFA reset; the user must enrol again.")}>Reset MFA</Button> : null}
            </span>) : "-" },
        ]} />
      {users.data ? <Pagination total={users.data.total} limit={25} offset={offset} onChange={setOffset} label="users" /> : null}
      {editing ? <UserDialog user={editing === "new" ? null : editing} roles={roles.data ?? []} isSelf={editing !== "new" && editing.id === me?.id}
        onClose={() => setEditing(null)} onSaved={(t) => { setEditing(null); setMsg({ tone: "success", text: t }); void users.refetch(); }} /> : null}
    </>
  );
}

function UserDialog({ user, roles, isSelf, onClose, onSaved }: { user: UserRow | null; roles: Role[]; isSelf: boolean; onClose: () => void; onSaved: (t: string) => void }) {
  const deps = useDepartments();
  const districts = useUnits("districts");
  const subdivisions = useUnits("subdivisions");
  const blocks = useUnits("blocks");
  const [f, setF] = useState({ username: user?.username ?? "", full_name: user?.full_name ?? "", designation: user?.designation ?? "", email: user?.email ?? "",
    department_id: user?.department_id ?? "", is_active: user?.is_active ?? true, password: "" });
  const [selRoles, setSelRoles] = useState<string[]>(user?.roles ?? []);
  const [scopes, setScopes] = useState<Scope[]>(user?.scopes ?? []);
  const [newScope, setNewScope] = useState<Scope>({ scope_type: "district" });
  const [err, setErr] = useState<string | null>(null);
  const target = (s: Scope) => {
    const find = (list: Array<{ id: string; name_en: string }> | undefined, id?: string | null) => list?.find((x) => x.id === id)?.name_en;
    return find(districts.data, s.district_id) ?? find(subdivisions.data, s.subdivision_id) ?? find(blocks.data, s.block_id) ?? find(deps.data, s.department_id) ?? "";
  };
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setErr(null);
    try {
      if (!user) {
        await apiSend("POST", "/iam/users", { username: f.username, full_name: f.full_name, designation: f.designation || null, email: f.email || null,
          department_id: f.department_id || null, roles: selRoles, scopes, temporary_password: f.password });
        onSaved("User created. They must change the temporary password at first sign-in.");
      } else {
        await apiSend("PATCH", `/iam/users/${user.id}`, { full_name: f.full_name, designation: f.designation || null, email: f.email || null, department_id: f.department_id || null, is_active: f.is_active });
        if (!isSelf && selRoles.join() !== user.roles.join()) await apiSend("PUT", `/iam/users/${user.id}/roles`, { roles: selRoles });
        await apiSend("PUT", `/iam/users/${user.id}/scopes`, { scopes });
        if (f.password) await apiSend("POST", `/iam/users/${user.id}/reset-password`, { temporary_password: f.password });
        onSaved("User updated.");
      }
    } catch (ex) {
      setErr(errorMessage(ex));
    }
  };
  const targetOptions = newScope.scope_type === "district" ? options(districts.data) : newScope.scope_type === "subdivision" ? options(subdivisions.data)
    : newScope.scope_type === "block" ? options(blocks.data) : newScope.scope_type === "department" ? options(deps.data) : [];
  const targetKey = `${newScope.scope_type}_id` as keyof Scope;
  return (
    <Dialog open title={user ? `Edit ${user.full_name}` : "Create user"} onClose={onClose}>
      {err ? <Alert tone="danger" title={err} className="mb-3" /> : null}
      <form onSubmit={submit} noValidate>
        {!user ? <TextField label="Username" required hint="Lower case letters, digits, dots, hyphens; 3-64 characters." value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} /> : null}
        <TextField label="Full name" required value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
        <TextField label="Designation" value={f.designation} onChange={(e) => setF({ ...f, designation: e.target.value })} />
        <TextField label="Official email" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        <SelectField label="Department" options={options(deps.data)} placeholder="None" value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })} />
        <fieldset className="mb-3 border-0 p-0">
          <legend className="font-semibold">Roles{isSelf ? " (you cannot change your own roles)" : ""}</legend>
          {roles.map((r) => <Checkbox key={r.code} label={r.name} disabled={isSelf} checked={selRoles.includes(r.code)}
            onChange={(e) => setSelRoles((s) => (e.target.checked ? [...s, r.code] : s.filter((x) => x !== r.code)).sort())} />)}
        </fieldset>
        <fieldset className="mb-3 border-0 p-0">
          <legend className="font-semibold">Area of responsibility</legend>
          {scopes.length ? <ul className="mt-1 pl-5">{scopes.map((s, i) => <li key={i}>{titleCase(s.scope_type)} {target(s)} <button type="button" className="text-link underline" onClick={() => setScopes(scopes.filter((_, j) => j !== i))}>Remove</button></li>)}</ul>
            : <p className="m-0 text-sm text-ink-muted">No area assigned: the user will see no grievances.</p>}
          <div className="mt-2 grid grid-cols-1 gap-x-3 md:grid-cols-[1fr_1fr_auto]">
            <SelectField label="Scope type" options={["district", "subdivision", "block", "department", "assigned", "own"].map((s) => ({ value: s, label: titleCase(s) }))} placeholder="Select"
              value={newScope.scope_type} onChange={(e) => setNewScope({ scope_type: e.target.value || "district" })} />
            {targetOptions.length ? <SelectField label="Unit" options={targetOptions} value={(newScope[targetKey] as string) ?? ""} onChange={(e) => setNewScope({ scope_type: newScope.scope_type, [targetKey]: e.target.value })} /> : <div />}
            <Button variant="secondary" className="mt-7 mb-4" disabled={Boolean(targetOptions.length) && !newScope[targetKey]} onClick={() => { setScopes([...scopes, newScope]); setNewScope({ scope_type: newScope.scope_type }); }}>Add</Button>
          </div>
        </fieldset>
        {user ? <Checkbox label="Account active" checked={f.is_active} disabled={isSelf} onChange={(e) => setF({ ...f, is_active: e.target.checked })} /> : null}
        <TextField label={user ? "Set a new temporary password (optional)" : "Temporary password"} type="password" autoComplete="new-password" required={!user}
          hint="The user must change it at first sign-in. At least 12 characters with three character types." value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        <Button type="submit">{user ? "Save changes" : "Create user"}</Button>
      </form>
    </Dialog>
  );
}
