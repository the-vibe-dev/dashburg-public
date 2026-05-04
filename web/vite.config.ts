import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const ROOT_ENV_PATH = path.resolve(__dirname, "../.env");

if (fs.existsSync(ROOT_ENV_PATH)) {
  const lines = fs.readFileSync(ROOT_ENV_PATH, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq).trim();
    const value = trimmed.slice(eq + 1);
    if (!(key in process.env)) {
      process.env[key] = value;
    }
  }
}

const DASHBURG_API_TARGET = process.env.VITE_DASHBURG_API_PROXY_TARGET ?? "http://127.0.0.1:8431";

export default defineConfig({
  envDir: "..",
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: DASHBURG_API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
});
