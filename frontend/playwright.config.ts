import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the full Docker Compose stack (nginx -> FastAPI ->
 * PostgreSQL/PostGIS/Redis); nothing is mocked. Start it first:
 *   docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
