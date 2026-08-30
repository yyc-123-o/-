import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { resolve } from "node:path";
import { fileURLToPath, URL } from "node:url";

const rootDir = fileURLToPath(new URL(".", import.meta.url));
// The platform mounts the diagnosis agent at /diagnosis and exposes path
// planning at /api/v1, so the frontend must use the unified platform service.
const apiTarget = process.env.VITE_DEV_API_TARGET || "http://127.0.0.1:8012";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": resolve(rootDir, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/diagnosis/api": apiTarget,
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
