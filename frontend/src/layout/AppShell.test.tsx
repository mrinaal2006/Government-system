import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { jsonResponse, mockApi, READY_OK, renderApp, shellSettled, SYSTEM_INFO } from "@/test/render";

describe("Application shell", () => {
  it("has skip link first, landmarks and the main navigation", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/");
    await shellSettled();
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    expect(skip).toHaveAttribute("href", "#main-content");
    await userEvent.tab();
    expect(skip).toHaveFocus();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main navigation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "District command dashboard" })).toBeInTheDocument();
  });

  it("shows unconfigured identity honestly and flags non-production environments", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/");
    await shellSettled();
    const banner = screen.getByRole("banner");
    expect(await within(banner).findByText(/development environment, not for official use/i)).toBeInTheDocument();
    expect(within(banner).getByText("Deployment identity not configured")).toBeInTheDocument();
    expect(within(banner).getByText("State government not configured")).toBeInTheDocument();
  });

  it("shows configured district and state identity", async () => {
    mockApi({
      "/api/v1/system/info": () =>
        jsonResponse({
          ...SYSTEM_INFO,
          environment: "production",
          deployment: { district_name: "Configured", district_name_local: null, state_name: "Some State", state_name_local: null },
        }),
    });
    renderApp("/");
    await shellSettled();
    const banner = screen.getByRole("banner");
    expect(await within(banner).findByText("District Administration, Configured")).toBeInTheDocument();
    expect(within(banner).getByText("Government of Some State")).toBeInTheDocument();
    expect(within(banner).queryByText(/not for official use/i)).toBeNull();
  });

  it("navigates, marks the current page and updates title, breadcrumbs and focus", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO), "/api/v1/health/ready": () => jsonResponse(READY_OK) });
    renderApp("/");
    await shellSettled();
    const nav = screen.getByRole("navigation", { name: "Main navigation" });
    await userEvent.click(within(nav).getByRole("link", { name: "System status" }));
    expect(await screen.findByRole("heading", { level: 1, name: "System status" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "System status" })).toHaveAttribute("aria-current", "page");
    expect(document.title).toBe("System status | DG-IMEWS");
    expect(screen.getByRole("main")).toHaveFocus();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Home" })).toBeInTheDocument();
  });

  it("future modules show an honest placeholder with no data", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/early-warning");
    await shellSettled();
    expect(await screen.findByText("Early warning alerts is not yet available")).toBeInTheDocument();
    expect(screen.getByText(/scheduled for development phase 6/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("unknown routes render the not-found page", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/no-such-page");
    await shellSettled();
    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });

  it("mobile menu toggle exposes its expanded state", async () => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO) });
    renderApp("/");
    await shellSettled();
    const toggle = screen.getByRole("button", { name: "Menu" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it.each(["/", "/system-status", "/design-system", "/accessibility"])("%s has no axe violations (jsdom)", async (path) => {
    mockApi({ "/api/v1/system/info": () => jsonResponse(SYSTEM_INFO), "/api/v1/health/ready": () => jsonResponse(READY_OK) });
    const { container } = renderApp(path);
    await shellSettled();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument());
    // Colour contrast is verified by tokens.test.ts and in a real browser by Playwright.
    const results = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
    expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
  });
});
