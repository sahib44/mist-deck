import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5181,
    proxy: {
      "/api": "http://localhost:8008",
      "/health": "http://localhost:8008",
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    exclude: ["tests/**", "node_modules/**"],
  },
});
