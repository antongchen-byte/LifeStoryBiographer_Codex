import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 120000,
  workers: 1,
  retries: 0,
  use: {
    baseURL: process.env.WEB_BASE ?? "http://localhost:3000",
    channel: "chrome",
    headless: true,
    viewport: { width: 1440, height: 1050 },
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
});
