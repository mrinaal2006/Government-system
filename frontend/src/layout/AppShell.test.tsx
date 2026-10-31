import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, OFFICER_PERMISSIONS, renderApp, session, shellSettled, SYSTEM_INFO } from "@/test/render";

describe("Application shell", () => {
  it("has skip link first, landmarks, main navigation and the signed-in user", async () => {
    mockApi();
    renderApp("/");
    await shellSettled();
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    await userEvent.tab();
    expect(skip).toHaveFocus();
    expect(screen.getByRole("banner")).toHaveTextContent("Test Officer");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 1, name: "District command dashboard" })).toBeInTheDocument();
  });

  it("redirects to sign-in when there is no session", async () => {
    mockApi({ "/api/v1/auth/me": () => jsonResponse({ error: { code: "not_authenticated", message: "Please sign in" } }, 401) });
    const { router } = renderApp("/grievances?status=open");
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toContain("next=%2Fgrievances");
  });

  it("shows unconfigured identity honestly and flags non-production environments", async () => {
    mockApi();
    renderApp("/");
    const banner = await screen.findByRole("banner");
    expect(await within(banner).findByText(/development environment, not for official use/i)).toBeInTheDocument();
    expect(within(banner).getByText("State government not configured")).toBeInTheDocument();
  });

  it("shows configured district and state identity", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse({ ...SYSTEM_INFO, environment: "production",
      deployment: { district_name: "Configured", district_name_local: null, state_name: "Some State", state_name_local: null } }) });
    renderApp("/");
    const banner = await screen.findByRole("banner");
    expect(await within(banner).findByText("District Administration, Configured")).toBeInTheDocument();
    expect(within(banner).queryByText(/not for official use/i)).toBeNull();
  });

  it("navigation reflects permissions and the officer home is the grievance register", async () => {
    mockApi({}, OFFICER_PERMISSIONS);
    const { router } = renderApp("/");
    await shellSettled();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    expect(within(nav).queryByRole("link", { name: "Command dashboard" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "Configuration" })).toBeNull();
    expect(within(nav).getByRole("link", { name: "Grievance register" })).toBeInTheDocument();
    await waitFor(() => expect(router.state.location.pathname).toBe("/grievances"));
  });

  it("shows an access message for screens outside the role (server still enforces)", async () => {
    mockApi({}, OFFICER_PERMISSIONS);
    renderApp("/admin/config");
    expect(await screen.findByRole("heading", { level: 1, name: "Access not permitted" })).toBeInTheDocument();
  });

  it("dashboard KPIs link to their filtered records", async () => {
    mockApi();
    renderApp("/");
    const overdue = await screen.findByRole("link", { name: /Overdue\s*3/ });
    expect(overdue).toHaveAttribute("href", "/grievances?overdue=true");
  });

  it("navigates, marks the current page and updates title, breadcrumbs and focus", async () => {
    mockApi();
    renderApp("/");
    await shellSettled();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    await userEvent.click(within(nav).getByRole("link", { name: "System status" }));
    expect(await screen.findByRole("heading", { level: 1, name: "System status" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "System status" })).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("System status | DG-IMEWS");
    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("unknown routes render the not-found page", async () => {
    mockApi();
    renderApp("/no-such-page");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });

  it("mobile menu toggle exposes its expanded state", async () => {
    mockApi();
    renderApp("/");
    const toggle = await screen.findByRole("button", { name: "Menu" });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("sign out ends the session", async () => {
    let signedOut = false;
    mockApi({
      "/api/v1/auth/me": () => (signedOut ? jsonResponse({ error: { code: "not_authenticated" } }, 401) : jsonResponse(session())),
      "/api/v1/auth/logout": () => { signedOut = true; return new Response(null, { status: 204 }); },
    });
    const { router } = renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(signedOut).toBe(true));
    await waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  });

  it.each(["/", "/grievances", "/grievances/new", "/system-status", "/accessibility", "/design-system"])("%s has no axe violations (jsdom)", async (path) => {
    mockApi();
    const { container } = renderApp(path);
    await shellSettled();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });

  it("login page has no axe violations", async () => {
    mockApi({ "/api/v1/auth/me": () => jsonResponse({ error: { code: "not_authenticated" } }, 401) });
    const { container } = renderApp("/login");
    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

export { session };
