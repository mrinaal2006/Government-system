import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, OFFICER_PERMISSIONS, renderApp, session } from "@/test/render";

const anonymous = () => jsonResponse({ error: { code: "not_authenticated", message: "Please sign in" } }, 401);
const noAxeViolations = async (container: HTMLElement) => {
  const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
};

describe("Officer sign-up", () => {
  it("is linked from sign-in, checks the confirmation, then signs straight in", async () => {
    let sent: Record<string, unknown> | null = null;
    let me: Response = anonymous();
    mockApi({
      "/api/v1/auth/me": () => me.clone(),
      "/api/v1/auth/signup": (_u, init) => {
        sent = JSON.parse(String(init?.body)) as Record<string, unknown>;
        me = jsonResponse(session(OFFICER_PERMISSIONS, ["data_entry_operator"]));
        return jsonResponse(session(OFFICER_PERMISSIONS, ["data_entry_operator"]), 201);
      },
    });
    const { container, router } = renderApp("/login");
    await userEvent.click(await screen.findByRole("link", { name: "Sign up" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign up" })).toBeInTheDocument();
    await noAxeViolations(container);
    await userEvent.type(screen.getByLabelText(/Username/), "Asha.K");
    await userEvent.type(screen.getByLabelText(/Full name/), "Asha K");
    await userEvent.type(screen.getByLabelText(/^Password/), "Long-Passw0rd-123");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "different");
    await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
    expect(await screen.findByText("The passwords do not match.")).toBeInTheDocument();
    expect(sent).toBeNull();
    await userEvent.clear(screen.getByLabelText(/Confirm password/));
    await userEvent.type(screen.getByLabelText(/Confirm password/), "Long-Passw0rd-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(sent).toEqual({ username: "asha.k", full_name: "Asha K", email: null, password: "Long-Passw0rd-123" });
  });

  it("sends the first account (Super Administrator) to MFA set-up", async () => {
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/auth/signup": () => jsonResponse(session([], ["super_admin"], "mfa_enrollment_required"), 201),
      "/api/v1/auth/mfa/setup": () => jsonResponse({ secret: "JBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/x?secret=JBSWY3DPEHPK3PXP" }),
    });
    const { router } = renderApp("/signup");
    await userEvent.type(await screen.findByLabelText(/Username/), "admin.dg");
    await userEvent.type(screen.getByLabelText(/Full name/), "Asha K");
    await userEvent.type(screen.getByLabelText(/^Password/), "Long-Passw0rd-123");
    await userEvent.type(screen.getByLabelText(/Confirm password/), "Long-Passw0rd-123");
    await userEvent.click(screen.getByRole("button", { name: "Sign up" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login/setup-mfa"));
  });

  it("keeps the link visible when the options call fails", async () => {
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/auth/signup/options": () => jsonResponse({ error: { code: "internal_error", message: "Server error" } }, 500),
    });
    renderApp("/login");
    expect(await screen.findByRole("link", { name: "Sign up" })).toBeInTheDocument();
  });

  it("hides the link only when the server turns sign-up off", async () => {
    mockApi({
      "/api/v1/auth/me": anonymous,
      "/api/v1/auth/signup/options": () => jsonResponse({ officer_signup_enabled: false, citizen_portal_enabled: false }),
    });
    renderApp("/login");
    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    await waitFor(() => expect(screen.queryByRole("link", { name: "Sign up" })).not.toBeInTheDocument());
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
