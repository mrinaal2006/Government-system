import { createHmac } from "node:crypto";

import { expect, type Page } from "@playwright/test";

/**
 * Credentials for the DEVELOPMENT demo accounts (synthetic data). Supplied by the
 * environment, never committed:
 *   E2E_PASSWORD      password printed by `python -m app.cli load-demo-data`
 *   E2E_TOTP_SECRETS  JSON map of username -> TOTP secret printed by the same command
 */
export const PASSWORD = process.env.E2E_PASSWORD ?? "";
const SECRETS: Record<string, string> = JSON.parse(process.env.E2E_TOTP_SECRETS ?? "{}");

function base32(secret: string): Buffer {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const c of secret.replace(/=+$/, "").toUpperCase()) bits += alphabet.indexOf(c).toString(2).padStart(5, "0");
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

/** RFC 6238 TOTP (SHA-1, 30 s, 6 digits). */
export function totp(secret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const h = createHmac("sha1", base32(secret)).update(counter).digest();
  const o = h[h.length - 1]! & 0xf;
  const code = ((h.readUInt32BE(o) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
  return code;
}

export async function signIn(page: Page, username: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  const secret = SECRETS[username];
  if (secret) {
    await expect(page.getByRole("heading", { name: "Verify your identity" })).toBeVisible();
    // TOTP codes are single-use per account (the server rejects replays). If the current
    // time step was already used (e.g. by another test process), wait for the next one.
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await page.getByLabel("Verification code").fill(totp(secret));
      await page.getByRole("button", { name: "Verify" }).click();
      const done = await page
        .getByRole("button", { name: "Sign out" })
        .waitFor({ timeout: 4000 })
        .then(() => true, () => false);
      if (done) break;
      await page.waitForTimeout(30_000 - (Date.now() % 30_000) + 500);
    }
  }
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

/**
 * Collects unexpected failures: script errors, CSP violations / console errors not caused
 * by an HTTP status, and HTTP responses >= 400 except the expected ones (401 from the
 * session probe before sign-in, 400 from a replayed MFA code that the helper retries).
 */
export function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => {
    const path = new URL(r.url()).pathname;
    const expected = (r.status() === 401 && path === "/api/v1/auth/me") || (r.status() === 400 && path === "/api/v1/auth/mfa/verify");
    if (r.status() >= 400 && !expected) errors.push(`${r.status()} ${r.request().method()} ${path}`);
  });
  return errors;
}
