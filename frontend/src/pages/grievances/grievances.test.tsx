import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, OFFICER_PERMISSIONS, renderApp } from "@/test/render";

const ROW = { id: "g1", reference_no: "DGI/2026/000001", subject: "Hand pump broken", status: "assigned", priority: "high", category: "Water",
  department: "Water Supply", block: "Block A", village: "Village X", assigned_officer: "Officer One", source: "Manual",
  registered_at: "2026-10-30T04:00:00Z", due_at: "2026-10-29T04:00:00Z", overdue: true, risk_level: "high", escalation_level: 1, reopened_count: 0 };

describe("Grievance register", () => {
  it("passes URL filters to the API and renders rows with overdue and risk shown as text", async () => {
    const fetchMock = mockApi({ "/api/v1/grievances": () => jsonResponse({ items: [ROW], total: 1, limit: 25, offset: 0 }) });
    renderApp("/grievances?overdue=true&status=assigned");
    const table = await screen.findByRole("table", { name: "Grievances" });
    expect(within(table).getByRole("link", { name: "DGI/2026/000001" })).toHaveAttribute("href", "/grievances/g1");
    expect(within(table).getByText(/Overdue:/)).toBeInTheDocument();
    expect(within(table).getAllByText("High")).toHaveLength(2); // priority and risk, both as text
    const call = fetchMock.mock.calls.map((c) => String(c[0])).find((u) => u.startsWith("/api/v1/grievances?"));
    expect(call).toContain("overdue=true");
    expect(call).toContain("status=assigned");
  });

  it("officers without grievance.create do not see the register button", async () => {
    mockApi({}, OFFICER_PERMISSIONS);
    renderApp("/grievances");
    await screen.findByRole("heading", { level: 1, name: "Grievance register" });
    expect(screen.queryByRole("link", { name: "Register grievance" })).toBeNull();
  });
});

describe("Register grievance form", () => {
  it("validates required fields and consent before submitting", async () => {
    const fetchMock = mockApi();
    renderApp("/grievances/new");
    await screen.findByRole("heading", { level: 1, name: "Register grievance" });
    await userEvent.type(screen.getByLabelText(/^Name/), "Citizen");
    await userEvent.click(screen.getByRole("button", { name: "Register grievance" }));
    expect(await screen.findByText("Please correct the highlighted fields.")).toBeInTheDocument();
    expect(screen.getByLabelText(/Received through/)).toHaveAccessibleDescription(/Select the channel/);
    expect(screen.getByLabelText(/^Subject/)).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText(/Record the complainant's consent/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "POST")).toBe(false);
  });

  it("submits and shows the reference number and possible duplicates", async () => {
    mockApi({
      "/api/v1/grievances": (_u, init) => init?.method === "POST"
        ? jsonResponse({ id: "g9", reference_no: "DGI/2026/000009", status: "registered", due_at: null, possible_duplicates: [{ grievance_id: "g1", similarity: 0.8 }] }, 201)
        : jsonResponse({ items: [], total: 0 }),
    });
    renderApp("/grievances/new");
    await screen.findByRole("option", { name: "Manual submission" });
    await userEvent.selectOptions(screen.getByLabelText(/Received through/), "s1");
    await userEvent.type(screen.getByLabelText(/^Subject/), "Street light not working");
    await userEvent.type(screen.getByLabelText(/^Description/), "The street light near the temple has not worked for a month.");
    await userEvent.click(screen.getByRole("button", { name: "Register grievance" }));
    expect(await screen.findByText("Reference number: DGI/2026/000009")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "similar grievance 1" })).toHaveAttribute("href", "/grievances/g1");
  });
});

describe("Grievance detail", () => {
  const detail = (actions: string[]) => ({
    id: "g1", reference_no: "DGI/2026/000001", subject: "Hand pump broken", description: "Details", summary: null, status: "assigned",
    priority: "high", received_at: "2026-10-30T04:00:00Z", registered_at: "2026-10-30T04:00:00Z", due_at: null, overdue: false,
    resolution_summary: null, reopened_count: 0, escalation_level: 0, location_text: null, duplicate_of_id: null, version: 3,
    source: null, category: null, subcategory: null, department: null, district: null, subdivision: null, block: null, gram_panchayat: null,
    village: null, municipality: null, ward: null, assigned_officer: { id: "u1", name: "Test Officer" }, created_by: null,
    complainant: { masked: true, name: "Restricted", mobile: "********10", email: null, address: null, consent_recorded: true },
    risk: null, sla_events: [], escalations: [], allowed_actions: actions,
  });
  const history = { status_history: [], assignments: [], comments: [], attachments: [], external_references: [], relationships: [] };

  it("shows only the actions the server allows and sends the version with transitions", async () => {
    let posted: unknown = null;
    mockApi({
      "/api/v1/grievances/g1": () => jsonResponse(detail(["start_work", "comment"])),
      "/api/v1/grievances/g1/history": () => jsonResponse(history),
      "/api/v1/grievances/g1/intelligence": () => jsonResponse({ classifications: [], duplicates: [], notice: "Suggestions only" }),
      "/api/v1/grievances/g1/transition": (_u, init) => { posted = JSON.parse(String(init?.body)); return jsonResponse({ id: "g1", status: "in_progress", version: 4 }); },
    }, OFFICER_PERMISSIONS);
    renderApp("/grievances/g1");
    const actions = await screen.findByRole("region", { name: "Actions" });
    expect(within(actions).getByRole("button", { name: "Start work" })).toBeInTheDocument();
    expect(within(actions).queryByRole("button", { name: /Assign/ })).toBeNull();
    expect(within(actions).queryByRole("button", { name: "Accept resolution" })).toBeNull();
    expect(screen.getByText("Personal details are restricted for your role.")).toBeInTheDocument();
    await userEvent.click(within(actions).getByRole("button", { name: "Start work" }));
    await userEvent.click(await screen.findByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(posted).toEqual({ action: "start_work", version: 3, note: null }));
  });
});
