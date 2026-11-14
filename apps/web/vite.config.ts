import path from "node:path";

import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

// The web app calls the API through /api so the browser never needs CORS in dev.
// MATTERPORT_SDK_KEY and DEMO_MODEL_ID live in the repo-root .env (gitignored); they are mapped to
// import.meta.env.VITE_* here so no value is in git. Local dev only: the SDK key is allowed on
// localhost, so do not ship a production bundle built with it.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, path.resolve(import.meta.dirname, "../.."), "");
  return {
    plugins: [react()],
    define: {
      "import.meta.env.VITE_MATTERPORT_SDK_KEY": JSON.stringify(
        env.MATTERPORT_SDK_KEY || undefined,
      ),
      "import.meta.env.VITE_DEMO_MODEL_ID": JSON.stringify(env.DEMO_MODEL_ID || undefined),
    },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
          rewrite: (p: string) => p.replace(/^\/api/, ""),
        },
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: ["./src/test/setup.ts"],
      css: false,
    },
  };
});
