import { defineConfig } from "@playwright/test";

/**
 * End-to-end journeys against a running stack: the web (`next start`) and the API Docker image
 * limited to 512 MB, as in production. CI starts both (see .github/workflows/ci.yml);
 * locally: E2E_BASE_URL=http://localhost:3000 npm run test:e2e
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
