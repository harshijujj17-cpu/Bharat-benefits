import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// React Fast Refresh + JSX transform. Without this config the installed
// @vitejs/plugin-react is never loaded and HMR is disabled.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
