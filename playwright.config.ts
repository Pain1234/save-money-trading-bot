import { defineConfig, devices } from "@playwright/test";

const PORT = 3015;
const STUB_PORT = 18080;
const BASE_URL = `http://localhost:${PORT}`;

const SESSION_SECRET = "x".repeat(32);
const AUTH_USERNAME = "monitor";
// bcrypt hash for password: testpass123
const AUTH_PASSWORD_HASH =
  "$2a$10$2aXtbAEG.N1RicofjkMbm.ddf6ivAWNrHd.oEhXrcBjmzlvfu4jyW";

export default defineConfig({
  testDir: "./tests/visual",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: BASE_URL,
    trace: "off",
    screenshot: "off",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: [
    {
      command: `node scripts/paper-api-stub.mjs`,
      url: `http://127.0.0.1:${STUB_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 30_000,
      env: {
        ...process.env,
        PAPER_API_STUB_PORT: String(STUB_PORT),
      },
    },
    {
      command: `npm run start -- -p ${PORT}`,
      url: BASE_URL,
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
      env: {
        ...process.env,
        SESSION_SECRET,
        AUTH_USERNAME,
        AUTH_PASSWORD_HASH,
        PRIVATE_PAPER_API_URL: `http://127.0.0.1:${STUB_PORT}`,
        NODE_ENV: "production",
      },
    },
  ],
});
