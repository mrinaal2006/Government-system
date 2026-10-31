import { expect, test } from "@playwright/test";

import { signIn, trackErrors } from "./helpers";

test.describe.configure({ mode: "serial" });
let reference = "";

test("data entry operator registers a grievance (markup stays inert text)", async ({ page }) => {
  let dialogs = 0;
  page.on("dialog", (d) => { dialogs += 1; void d.dismiss(); });
  await signIn(page, "demo.deo");
  await page.goto("/grievances/new");
  await page.getByLabel(/Received through/).selectOption({ label: "Manual submission" });
  await page.getByLabel(/^Subject/).fill(`[E2E TEST] Hand pump broken <img src=x onerror=alert(1)>`);
  await page.getByLabel(/^Description/).fill("[E2E TEST DATA] The hand pump near the anganwadi has not worked for six days; water needed urgently.");
  await page.getByLabel(/^Category/).selectOption({ label: "Drinking water supply (demo)" });
  await page.getByLabel("Block").selectOption({ label: "Amritpur (demo)" });
  await page.getByLabel("Gram panchayat").selectOption({ index: 1 });
  await page.getByLabel("Village").selectOption({ index: 1 });
  await page.getByLabel(/^Mobile number/).fill("9000012345");
  await page.getByLabel(/consented/).check();
  await page.getByRole("button", { name: "Register grievance" }).click();
  const ok = page.getByText(/Reference number: DGI\/\d{4}\/\d{6}/);
  await expect(ok).toBeVisible();
  reference = ((await ok.innerText()).match(/DGI\/\d{4}\/\d{6}/) ?? [""])[0];
  await page.getByRole("link", { name: "Open the grievance" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toContainText("<img src=x onerror=alert(1)>");
  expect(dialogs).toBe(0);
});

test("DM assigns, officer resolves, DM verifies; history is complete", async ({ page, browser }) => {
  expect(reference).not.toBe("");
  const errors = trackErrors(page);
  await signIn(page, "demo.dm");
  await page.goto(`/grievances?q=${encodeURIComponent(reference)}`);
  await page.getByRole("link", { name: reference }).click();
  const url = page.url();
  await page.getByRole("button", { name: "Assign" }).click();
  const officerSelect = page.getByLabel(/^Officer/);
  const value = await officerSelect.locator("option", { hasText: "Demo Officer 1 - Water Supply" }).getAttribute("value");
  await officerSelect.selectOption(value!);
  await page.getByRole("dialog").getByRole("button", { name: "Assign" }).click();
  await expect(page.getByText("Assigned.")).toBeVisible();
  await expect(page.getByText("Assigned", { exact: true }).first()).toBeVisible();

  const officerCtx = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: new URL(url).origin });
  const officer = await officerCtx.newPage();
  await signIn(officer, "demo.officer.water1");
  await officer.goto(new URL(url).pathname);
  await officer.getByRole("button", { name: "Start work" }).click();
  await officer.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(officer.getByText("Start work: done.")).toBeVisible();
  await officer.getByRole("button", { name: "Submit resolution" }).click();
  await officer.getByLabel(/Action taken/).fill("[E2E TEST] Pump repaired by the mechanic; water flow verified on site.");
  await officer.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(officer.getByText("Submit resolution: done.")).toBeVisible();
  await expect(officer.getByRole("button", { name: "Accept resolution" })).toHaveCount(0);
  await officerCtx.close();

  await page.reload();
  await page.getByRole("button", { name: "Accept resolution" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Accept resolution: done.")).toBeVisible();
  await expect(page.getByText("Resolved", { exact: true }).first()).toBeVisible();
  await page.getByRole("tab", { name: "History" }).click();
  const history = page.getByRole("tabpanel");
  for (const s of ["Registered", "Assigned", "In progress", "Resolution submitted", "Resolved"]) {
    await expect(history.getByText(s, { exact: true }).first()).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("DM generates an executive summary PDF and downloads it", async ({ page }) => {
  await signIn(page, "demo.dm");
  await page.goto("/reports");
  await page.getByRole("button", { name: "Generate report" }).click();
  await expect(page.getByText("Report requested.")).toBeVisible();
  const link = page.getByRole("table", { name: "My reports" }).getByRole("link", { name: /executive_summary_.*\.pdf/ }).first();
  await expect(link).toBeVisible({ timeout: 30_000 });
  const res = await page.request.get((await link.getAttribute("href"))!);
  expect(res.status()).toBe(200);
  expect((await res.body()).subarray(0, 4).toString()).toBe("%PDF");
});
