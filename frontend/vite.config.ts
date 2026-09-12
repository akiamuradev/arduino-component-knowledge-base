import react from "@vitejs/plugin-react";
import { configDefaults, defineConfig } from "vitest/config";
import { currentBuildInfo } from "./build-metadata.ts";

export default defineConfig(() => {
  const info = currentBuildInfo();
  return {
    define: {
      "import.meta.env.VITE_APP_VERSION": JSON.stringify(info.version),
      "import.meta.env.VITE_COMMIT_SHA": JSON.stringify(info.commitSha),
      "import.meta.env.VITE_BUILD_DATE": JSON.stringify(info.buildDate),
    },
    plugins: [react(), {
      name: "ackb-build-provenance",
      generateBundle() {
        this.emitFile({ type: "asset", fileName: "build-info.json", source: JSON.stringify(info) });
      },
    }],
    build: {
      assetsInlineLimit: 0,
    },
    server: {
      proxy: {
        "/api": {
          target: "http://127.0.0.1:8000",
          changeOrigin: false,
        },
      },
    },
    test: {
      environment: "jsdom",
      exclude: [...configDefaults.exclude, "e2e/**"],
      setupFiles: "./src/test/setup.ts",
      restoreMocks: true,
    },
  };
});
