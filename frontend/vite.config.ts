import react from "@vitejs/plugin-react";
import { execFileSync } from "node:child_process";
import { loadEnv } from "vite";
import { configDefaults, defineConfig } from "vitest/config";

function currentCommit(): string {
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "не указан";
  }
}

export default defineConfig(({ mode }) => {
  const env = { ...loadEnv(mode, process.cwd(), "VITE_"), ...process.env };
  const commitSha = (env.VITE_COMMIT_SHA ?? "").trim();
  const buildDate = (env.VITE_BUILD_DATE ?? "").trim();
  return {
    define: {
      "import.meta.env.VITE_COMMIT_SHA": JSON.stringify(commitSha === "" ? currentCommit() : commitSha),
      "import.meta.env.VITE_BUILD_DATE": JSON.stringify(buildDate === "" ? new Date().toISOString().replace(/\.\d{3}Z$/, "Z") : buildDate),
    },
    plugins: [react()],
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
