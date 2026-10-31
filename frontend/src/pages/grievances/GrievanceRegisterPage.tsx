import { useState, type FormEvent } from "react";
import { Link } from "react-router";

import { Alert, Button, Checkbox, PageHeader, Panel, SelectField, TextAreaField, TextField } from "@/design-system";
import { apiSend, errorMessage, fieldErrors } from "@/lib/api/client";
import { LocationPicker, type LocationValue } from "@/lib/LocationPicker";
import { options, useCategories, useSources } from "@/lib/reference";

interface Created { id: string; reference_no: string; status: string; due_at: string | null; possible_duplicates: Array<{ grievance_id: string; similarity: number }> }

const EMPTY = { source_id: "", subject: "", description: "", category_id: "", subcategory_id: "", priority: "normal", location_text: "",
  received_at: "", name: "", mobile: "", email: "", address: "", consent: false };

export function GrievanceRegisterPage() {
  const sources = useSources();
  const cats = useCategories();
  const [form, setForm] = useState(EMPTY);
  const [location, setLocation] = useState<LocationValue>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [created, setCreated] = useState<Created | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof EMPTY, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));
  const subs = (cats.data ?? []).filter((c) => c.parent_id && c.parent_id === form.category_id);

  const validate = () => {
    const e: Record<string, string> = {};
    if (!form.source_id) e.source_id = "Select the channel through which the grievance was received.";
    if (form.subject.trim().length < 5) e.subject = "Enter a subject of at least 5 characters.";
    if (form.description.trim().length < 10) e.description = "Describe the grievance in at least 10 characters.";
    if (form.mobile && !/^\+?[0-9 ]{10,15}$/.test(form.mobile)) e["complainant.mobile"] = "Enter a valid mobile number (10-15 digits).";
    if ((form.name || form.mobile || form.address) && !form.consent) e.consent = "Record the complainant's consent before storing personal details.";
    return e;
  };

  const submit = async (ev: FormEvent) => {
    ev.preventDefault();
    setFailure(null);
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) {
      setFailure("Please correct the highlighted fields.");
      return;
    }
    setBusy(true);
    try {
      const hasPerson = form.name || form.mobile || form.email || form.address;
      const result = await apiSend<Created>("POST", "/grievances", {
        source_id: form.source_id, subject: form.subject, description: form.description,
        category_id: form.category_id || null, subcategory_id: form.subcategory_id || null, priority: form.priority,
        location: Object.fromEntries(Object.entries(location).filter(([, v]) => v)), location_text: form.location_text || null,
        received_at: form.received_at ? new Date(form.received_at).toISOString() : null,
        complainant: hasPerson ? { name: form.name || null, mobile: form.mobile || null, email: form.email || null, address: form.address || null, consent_recorded: form.consent } : null,
      });
      setCreated(result);
      setForm(EMPTY);
      setLocation({});
    } catch (err) {
      setErrors(fieldErrors(err));
      setFailure(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  if (created) {
    return (
      <>
        <PageHeader title="Grievance registered" />
        <Alert tone="success" title={`Reference number: ${created.reference_no}`} live>
          Give this reference to the complainant. {created.due_at ? "A resolution time limit has been applied." : "No resolution time limit is configured for this category."}
        </Alert>
        {created.possible_duplicates.length ? (
          <Alert tone="warning" title="Possible duplicates found" className="mt-3">
            Review these before assigning:{" "}
            {created.possible_duplicates.map((d, i) => (
              <span key={d.grievance_id}>{i ? ", " : ""}<Link to={`/grievances/${d.grievance_id}`}>similar grievance {i + 1}</Link> ({Math.round(d.similarity * 100)}% similar)</span>
            ))}
          </Alert>
        ) : null}
        <div className="mt-4 flex gap-3">
          <Link to={`/grievances/${created.id}`}>Open the grievance</Link>
          <Button variant="secondary" onClick={() => setCreated(null)}>Register another</Button>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Register grievance" description="Fields marked (required) must be completed. Personal details are encrypted and visible only to authorised officers." />
      {failure ? <Alert tone="danger" title={failure} className="mb-4" /> : null}
      <form onSubmit={submit} noValidate className="grid grid-cols-1 gap-5">
        <Panel title="Grievance details">
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            <SelectField label="Received through" required options={options(sources.data)} value={form.source_id} onChange={(e) => set("source_id", e.target.value)} error={errors.source_id} />
            <TextField label="Date and time received" type="datetime-local" hint="Leave blank if received now." value={form.received_at} onChange={(e) => set("received_at", e.target.value)} error={errors.received_at} />
          </div>
          <TextField label="Subject" required maxLength={300} value={form.subject} onChange={(e) => set("subject", e.target.value)} error={errors.subject} />
          <TextAreaField label="Description" required maxLength={20000} hint="Record the complaint as stated. Do not add personal opinions." value={form.description} onChange={(e) => set("description", e.target.value)} error={errors.description} />
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-3">
            <SelectField label="Category" options={options(cats.data?.filter((c) => !c.parent_id))} placeholder="Not yet classified" value={form.category_id}
              onChange={(e) => setForm((f) => ({ ...f, category_id: e.target.value, subcategory_id: "" }))} />
            <SelectField label="Subcategory" options={options(subs)} placeholder={subs.length ? "Select" : "None available"} value={form.subcategory_id} disabled={!subs.length}
              onChange={(e) => set("subcategory_id", e.target.value)} />
            <SelectField label="Priority" options={[{ value: "low", label: "Low" }, { value: "normal", label: "Normal" }, { value: "high", label: "High" }, { value: "urgent", label: "Urgent" }]}
              placeholder="Normal" value={form.priority} onChange={(e) => set("priority", e.target.value || "normal")} />
          </div>
        </Panel>
        <Panel title="Location">
          <LocationPicker value={location} onChange={setLocation} errors={errors} />
          <TextField label="Address or landmark (optional)" maxLength={500} value={form.location_text} onChange={(e) => set("location_text", e.target.value)} />
        </Panel>
        <Panel title="Complainant (optional)" description="Stored encrypted. Only officers with permission can view it.">
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            <TextField label="Name" maxLength={200} value={form.name} onChange={(e) => set("name", e.target.value)} />
            <TextField label="Mobile number" inputMode="tel" maxLength={15} value={form.mobile} onChange={(e) => set("mobile", e.target.value)} error={errors["complainant.mobile"]} />
            <TextField label="Email" type="email" maxLength={200} value={form.email} onChange={(e) => set("email", e.target.value)} error={errors["complainant.email"]} />
            <TextField label="Address" maxLength={1000} value={form.address} onChange={(e) => set("address", e.target.value)} />
          </div>
          <Checkbox label="The complainant consented to these details being recorded for handling this grievance" checked={form.consent}
            onChange={(e) => set("consent", e.target.checked)} hint={errors.consent} />
        </Panel>
        <div>
          <Button type="submit" busy={busy} busyLabel="Registering…">Register grievance</Button>
        </div>
      </form>
    </>
  );
}
