import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, renderApp } from "@/test/render";

const anonymous = () => jsonResponse({ error: { code: "not_authenticated", message: "Please sign in" } }, 401);
const noAxeViolations = async (container: HTMLElement) => {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
};

describe("Officer access request", () => {
  it("is linked from sign-in, checks the confirmation and submits the request", async () => {
    let sent: Record<string, unknown> | null = null;
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/auth/signup": (_u, init) => {
        sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
        return jsonResponse({ status: "pending" }, 202);
      },
    });
    const { container } = renderApp("/login");
    await userEvent.click(await screen.findByRole("link", { name: "Request access" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Request access" })).toBeInTheDocument();
    await noAxeViolations(container);
    await userEvent.type(screen.getByLabelText(/Username/), "Asha.K");
    await userEvent.type(screen.getByLabelText(/Full name/), "Asha K");
    await userEvent.type(screen.getByLabelText(/Designation/), "Block Officer");
    await userEvent.type(screen.getByLabelText(/Official email/), "asha@example.gov.in");
    await userEvent.selectOptions(screen.getByLabelText(/Role requested/), "department_officer");
    await userEvent.type(screen.getByLabelText(/^Password/), "Long-Passw0rd-123");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "different");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByText("The passwords do not match.")).toBeInTheDocument();
    expect(sent).toBeNull();
    await userEvent.clear(screen.getByLabelText(/Confirm password/));
    await userEvent.type(screen.getByLabelText(/Confirm password/), "Long-Passw0rd-123");
    await userEvent.click(screen.getByRole("button", { name: "Submit request" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Request submitted" })).toBeInTheDocument();
    expect(sent).toMatchObject({ username: "asha.k", requested_role: "department_officer", department_id: null });
    expect(sent).not.toHaveProperty("confirm");
  });
});

describe("Citizen portal", () => {
  it("registers, shows the development code, verifies and signs in", async () => {
    let me: Response = anonymous();
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/citizen/me": () => me.clone(),
      "/api/v1/citizen/config": () => jsonResponse({ consent_version: "2026-10", otp_ttl_minutes: 10 }),
      "/api/v1/citizen/register": () => jsonResponse({ message: "sent", development_otp: "123456" }, 202),
      "/api/v1/citizen/verify": (_u, init) => {
        expect(JSON.parse(String(init?.body))).toEqual({ mobile: "9876543210", code: "123456" });
        return jsonResponse({ verified: true });
      },
      "/api/v1/citizen/login": () => {
        me = jsonResponse({ id: "c1", name: "Asha", mobile: "******3210", verified: true });
        return me.clone();
      },
      "/api/v1/citizen/grievances": () => jsonResponse([]),
    });
    const { container, router } = renderApp("/citizen");
    await userEvent.click(await screen.findByRole("link", { name: "Create an account" }));
    await screen.findByRole("heading", { level: 1, name: "Create an account" });
    await noAxeViolations(container);
    await userEvent.type(screen.getByLabelText(/Mobile number/), "9876543210");
    await userEvent.type(screen.getByLabelText(/Your name/), "Asha");
    await userEvent.type(screen.getByLabelText(/^Password/), "Long-Passw0rd-123");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "Long-Passw0rd-123");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Please accept to continue.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/I agree/));
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByText(/Development only: your code is 123456/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/6-digit code/), "123456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(await screen.findByText(/Your mobile number is verified/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Password/), "Long-Passw0rd-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("heading", { level: 1, name: "My grievances" })).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe("/citizen"));
  });

  it("sends the citizen CSRF cookie and shows only the public status", async () => {
    document.cookie = "dgi_ccsrf=citizen-token; path=/";
    document.cookie = "dgi_csrf=officer-token; path=/";
    let header: string | null = null;
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/citizen/me": () => jsonResponse({ id: "c1", name: "Asha", mobile: "******3210", verified: true }),
      "/api/v1/citizen/reference/categories": () => jsonResponse([{ id: "cat1", name_en: "Water supply" }]),
      "/api/v1/citizen/reference/units/districts": () => jsonResponse([]),
      "/api/v1/citizen/reference/units/blocks": () => jsonResponse([]),
      "/api/v1/citizen/reference/units/municipalities": () => jsonResponse([]),
      "/api/v1/citizen/grievances": (_u, init) => {
        header = new Headers(init?.headers).get("X-CSRF-Token");
        return jsonResponse({ id: "g1", reference_no: "DGI/2026/000001", status_label: "Received" }, 201);
      },
      "/api/v1/citizen/grievances/g1": () => jsonResponse({ id: "g1", reference_no: "DGI/2026/000001", subject: "No water", description: "The hand pump is broken.",
        status: "registered", status_label: "Received", registered_at: "2026-10-31T06:30:00+00:00", updated_at: "2026-10-31T06:30:00+00:00",
        responsible_office: "Public Health Engineering", resolution: null, timeline: [{ status_label: "Received", at: "2026-10-31T06:30:00+00:00" }] }),
    });
    const { container } = renderApp("/citizen/new");
    await userEvent.type(await screen.findByLabelText(/Subject/), "No water");
    await userEvent.type(screen.getByLabelText(/Description/), "The hand pump is broken for two weeks.");
    await noAxeViolations(container);
    await userEvent.click(screen.getByRole("button", { name: "Submit grievance" }));
    expect(await screen.findByText(/Your reference number is DGI\/2026\/000001/)).toBeInTheDocument();
    expect(header).toBe("citizen-token");
    expect(await screen.findByText("Public Health Engineering")).toBeInTheDocument();
  });
});
