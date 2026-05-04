import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const DASHBURG_API_TARGET = process.env.VITE_DASHBURG_API_PROXY_TARGET ?? "http://127.0.0.1:8431";
export default defineConfig({
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
