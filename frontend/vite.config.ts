import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // Backend dev server (see backend/app/config.py BACKEND_PORT).
      "/api": "http://127.0.0.1:8011",
    },
  },
});
