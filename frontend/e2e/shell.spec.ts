import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

/** Fail on any console error, which includes Content-Security-Policy violations. */
function trackConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(err.message));
  return errors;
}

async function axe(page: Page) {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return results.violations.map((v) => `${v.id} (${v.nodes.length}): ${v.help}`);
}

test("shell renders under the production CSP without console errors", async ({ page }) => {
  const errors = trackConsoleErrors(page);
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain("script-src 'self'");
  await expect(page.getByRole("heading", { level: 1, name: "District command dashboard" })).toBeVisible();
  await expect(page.getByRole("banner")).toContainText("District Grievance Intelligence");
  await expect(page.getByText(/DG-IMEWS version 0\.1\.0/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("system status reflects the live backend", async ({ page }) => {
  await page.goto("/system-status");
  await expect(page.getByText("All services are operational")).toBeVisible();
  const table = page.getByRole("table", { name: "Service readiness" });
  await expect(table.getByText("Operational")).toHaveCount(4);
  await expect(table).toContainText("PostGIS spatial extension");
  await expect(page.getByText(/IST\./)).toBeVisible();
});

test("deep links are served by the SPA fallback and show honest placeholders", async ({ page }) => {
  await page.goto("/grievances/new");
  await expect(page.getByRole("heading", { level: 1, name: "Register grievance" })).toBeVisible();
  await expect(page.getByText("Register grievance is not yet available")).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toContainText("Grievance register");
});

test("skip link is the first tab stop and moves focus to main content", async ({ page, isMobile }) => {
  test.skip(isMobile, "keyboard flow is verified on desktop");
  await page.goto("/");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#main-content$/);
  await expect(page.locator("#main-content")).toBeFocused();
});

for (const path of ["/", "/system-status", "/accessibility", "/reports"]) {
  test(`no WCAG 2.1 AA axe violations on ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByText(/DG-IMEWS version/)).toBeVisible();
    expect(await axe(page)).toEqual([]);
  });
}

test("high-contrast mode has no axe violations and persists across reloads", async ({ page }) => {
  await page.goto("/system-status");
  await page.getByRole("button", { name: "High contrast" }).click();
  await page.getByRole("button", { name: "A++ (larger text size)" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-contrast", "high");
  await expect(page.getByText("All services are operational")).toBeVisible();
  expect(await axe(page)).toEqual([]);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-contrast", "high");
  await expect(page.locator("html")).toHaveAttribute("data-text-scale", "larger");
});

test("content reflows at 320 CSS px without horizontal scrolling (WCAG 1.4.10)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 640 });
  for (const path of ["/", "/system-status"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }
  const menu = page.getByRole("button", { name: "Menu" });
  await expect(menu).toHaveAttribute("aria-expanded", "false");
  await menu.click();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "Accessibility statement" }).count();
  await page.getByRole("navigation", { name: "Main navigation" }).getByRole("link", { name: "System status" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "System status" })).toBeVisible();
});

test("API errors use the standard envelope with a request ID", async ({ request }) => {
  const res = await request.get("/api/v1/does-not-exist");
  expect(res.status()).toBe(404);
  const body = await res.json();
  expect(body.error.code).toBe("not_found");
  expect(body.error.request_id).toMatch(/^[0-9a-f]{32}$/);
  expect(res.headers()["x-request-id"]).toBe(body.error.request_id);
});
