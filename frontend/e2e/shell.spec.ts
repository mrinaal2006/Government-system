import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { signIn, trackErrors } from "./helpers";

async function axe(page: Page) {
  const r = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return r.violations.map((v) => `${v.id} (${v.nodes.length}): ${v.help} -> ${v.nodes[0]?.target.join(" ")}`);
}

test("sign-in page renders under the strict CSP with no errors and no axe violations @mobile", async ({ page }) => {
  const errors = trackErrors(page);
  const res = await page.goto("/");
  expect(res?.headers()["content-security-policy"]).toContain("script-src 'self'");
  await expect(page.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
  expect(await axe(page)).toEqual([]);
  expect(errors).toEqual([]);
});

test("wrong password gives a generic message", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Username").fill("demo.deo");
  await page.getByLabel(/^Password/).fill("not-the-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText(/Invalid username or password/);
});

test("DM signs in with MFA; KPIs open their filtered records; sign out protects pages", async ({ page }) => {
  const errors = trackErrors(page);
  await signIn(page, "demo.dm");
  await expect(page.getByRole("heading", { level: 1, name: "District command dashboard" })).toBeVisible();
  const overdue = page.getByRole("link", { name: /^Overdue/ });
  const value = Number((await overdue.innerText()).match(/\d+/)?.[0]);
  await overdue.click();
  await expect(page).toHaveURL(/overdue=true/);
  await expect(page.getByText(new RegExp(`of ${value} grievances`))).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.goto("/grievances");
  await expect(page).toHaveURL(/\/login\?next=%2Fgrievances/);
  expect(errors).toEqual([]);
});

test("officer sees only permitted navigation; admin screens and APIs are refused", async ({ page }) => {
  await signIn(page, "demo.officer.water1");
  const nav = page.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("link", { name: "Grievance register" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Configuration" })).toHaveCount(0);
  await expect(nav.getByRole("link", { name: "Command dashboard" })).toHaveCount(0);
  await page.goto("/admin/config");
  await expect(page.getByRole("heading", { name: "Access not permitted" })).toBeVisible();
  const api = await page.request.get("/api/v1/iam/users");
  expect(api.status()).toBe(403);
});

const AUTH_PAGES = ["/", "/grievances", "/grievances/new", "/early-warning", "/gis", "/performance", "/reports",
  "/notifications", "/admin/users", "/audit", "/system-status", "/accessibility"];

test("authenticated pages have no WCAG 2.1 AA axe violations (standard and high contrast)", async ({ page }) => {
  await signIn(page, "demo.dm");
  for (const path of AUTH_PAGES) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(await axe(page), path).toEqual([]);
  }
  await page.getByRole("button", { name: "High contrast" }).click();
  for (const path of ["/", "/grievances", "/early-warning"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await axe(page), `${path} (high contrast)`).toEqual([]);
  }
  await page.getByRole("button", { name: "High contrast" }).click();
});

test("admin configuration and audit pages are accessible to the super administrator", async ({ page }) => {
  await signIn(page, "demo.admin");
  for (const path of ["/admin/config", "/admin/users", "/audit"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect(await axe(page), path).toEqual([]);
  }
  await page.goto("/audit");
  await page.getByRole("button", { name: "Verify integrity" }).click();
  await expect(page.getByText(/Integrity verified/)).toBeVisible();
  const g = await page.request.get("/api/v1/grievances");
  expect(g.status()).toBe(403); // super admin is separated from citizen data
});

test("content reflows at 320 px without horizontal scrolling @mobile", async ({ page }) => {
  await signIn(page, "demo.dm");
  await page.setViewportSize({ width: 320, height: 700 });
  for (const path of ["/", "/grievances", "/early-warning"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, path).toBeLessThanOrEqual(0);
  }
});
