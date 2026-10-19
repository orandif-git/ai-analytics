import { existsSync } from "node:fs";
import { defineConfig } from "@playwright/test";

// The sandbox/CI ships its own Chromium; use it when present instead of downloading one.
const candidates = [process.env.PW_CHROMIUM, "/opt/pw-browsers/chromium-1194/chrome-linux/chrome", "/opt/pw-browsers/chromium/chrome-linux/chrome"];
const executablePath = candidates.find((p) => p && existsSync(p));

export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: process.env.AIA_E2E_WEB, launchOptions: executablePath ? { executablePath } : {}, trace: "retain-on-failure" },
});
