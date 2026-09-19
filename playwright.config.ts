import { defineConfig, devices } from "@playwright/test";

const backendURL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:18168";
const e2eProfile = process.env.E2E_PROFILE ?? "full";
const reuseExistingServer = false;

if (e2eProfile !== "full" && e2eProfile !== "smoke") {
  throw new Error(`Unsupported E2E_PROFILE: ${e2eProfile}. Expected full or smoke.`);
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  failOnFlakyTests: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: [["list"], ["html", { open: "never" }], ["./scripts/e2e/summary-reporter.mjs"]],
  use: {
    trace: process.env.CI ? "off" : "retain-on-failure",
    screenshot: "only-on-failure",
    video: process.env.CI ? "off" : "retain-on-failure",
  },
  projects: [
    {
      name: "admin-desktop",
      use: { ...devices["Desktop Chrome"], baseURL: "http://127.0.0.1:3001" },
    },
    {
      name: "admin-mobile",
      use: { ...devices["Pixel 7"], baseURL: "http://127.0.0.1:3001" },
    },
  ],
  webServer: process.env.E2E_MANAGED_SERVERS === "1" ? undefined : [
    {
      command: "node scripts/e2e/admin-preview.mjs",
      url: "http://127.0.0.1:3001",
      reuseExistingServer,
      timeout: 120_000,
      env: { E2E_BACKEND_URL: backendURL },
    },
  ],
});
