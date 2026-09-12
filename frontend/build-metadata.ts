import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

export function resolveBuildInfo(version: string, gitCommit: string | undefined,
  dockerCommit: string | undefined, now: Date) {
  const commitSha = gitCommit ?? dockerCommit;
  if (!commitSha || !/^[a-f0-9]{40}$/.test(commitSha)) {
    throw new Error("Missing verified Git SHA. Build Docker images with scripts/build_images.py.");
  }
  return { version, commitSha, buildDate: now.toISOString().replace(/\.\d{3}Z$/, "Z") };
}

export function currentBuildInfo() {
  // package.json is release-contract checked against pyproject.toml. Never load
  // version, revision or time from .env / legacy ACKB_* / VITE_* overrides.
  const metadata = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
  let gitCommit: string | undefined;
  try {
    gitCommit = execFileSync("git", ["rev-parse", "HEAD"], {
      cwd: new URL(".", import.meta.url), encoding: "utf8", stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    // Docker deliberately has no Git directory. The build wrapper supplies HEAD.
  }
  return resolveBuildInfo(metadata.version, gitCommit, process.env.ACKB_BUILD_GIT_SHA, new Date());
}
