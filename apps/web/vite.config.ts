import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The web app calls the API through /api so the browser never needs CORS in dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
