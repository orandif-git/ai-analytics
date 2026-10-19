import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In production Caddy serves the built files and proxies /api to the API (stripping the prefix).
// The dev server does the same so the app code never needs to know the difference.
const proxy = {
  "/api": { target: process.env.AIA_API ?? "http://127.0.0.1:8000", rewrite: (p: string) => p.replace(/^\/api/, "") },
};

export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
  test: { include: ["tests/**/*.test.ts"] },
});
