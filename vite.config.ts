import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";

// https://vitejs.dev/config/
export default defineConfig(() => ({
  server: {
    host: "::",
    port: 8080,
    hmr: { overlay: false },
    proxy: {
      // Forward /api/* verbatim. Backend routes are namespaced under /api
      // (e.g. /api/telemetry, /api/simulate, /api/chat) — do NOT rewrite.
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      // The backend's /health probe lives at the root.
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
    dedupe: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime", "@tanstack/react-query", "@tanstack/query-core"],
  },
  build: {
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // Keep the largest 3rd-party deps in their own chunks so the main
        // bundle stays small and aggressive caching works between deploys.
        manualChunks: {
          firebase: ["firebase/app", "firebase/auth", "firebase/database"],
          react: ["react", "react-dom", "react-router-dom"],
          charts: ["recharts"],
          ui: [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-popover",
            "@radix-ui/react-select",
            "@radix-ui/react-tabs",
            "@radix-ui/react-tooltip",
          ],
        },
      },
    },
  },
}));
