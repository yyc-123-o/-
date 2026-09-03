import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "node:path";
import { fileURLToPath, URL } from "node:url";

const rootDir = fileURLToPath(new URL(".", import.meta.url));
// The platform mounts the diagnosis agent at /diagnosis and exposes path
// planning at /api/v1, so the frontend must use the unified platform service.
const apiTarget = process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8000";
const diagnosisApiTarget = process.env.VITE_DEV_DIAGNOSIS_API_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(rootDir, "src"),
    },
  },
  server: {
    // 5173 is occupied by another local project in the shared development setup.
    // Fail clearly instead of silently serving this platform on an unexpected port.
    port: 5174,
    strictPort: true,
    proxy: {
      "/api": apiTarget,
      "/diagnosis/api": diagnosisApiTarget,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
