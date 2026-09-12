import { afterEach, describe, expect, it, vi } from "vitest";
import { currentBuildInfo, resolveBuildInfo } from "./build-metadata";

vi.mock("node:fs", () => {
  const mocked = { readFileSync: () => '{"version":"1.6.0"}' };
  return { ...mocked, default: mocked };
});
vi.mock("node:child_process", () => {
  const mocked = { execFileSync: () => "a".repeat(40) };
  return { ...mocked, default: mocked };
});

const actual = "a".repeat(40);
const stale = "b".repeat(40);
const now = new Date("2026-09-12T01:02:03.456Z");

afterEach(() => { vi.unstubAllEnvs(); });

describe("build provenance", () => {
  it("uses project version, real Git and the current build clock", () => {
    expect(resolveBuildInfo("1.6.0", actual, stale, now)).toEqual({
      version: "1.6.0", commitSha: actual, buildDate: "2026-09-12T01:02:03Z",
    });
  });
  it("requires a full build-wrapper SHA when Git is unavailable in Docker", () => {
    expect(resolveBuildInfo("1.6.0", undefined, actual, now).commitSha).toBe(actual);
    for (const value of [undefined, "", "b1c81e7", "не указан"]) {
      expect(() => resolveBuildInfo("1.6.0", undefined, value, now)).toThrow("Git SHA");
    }
  });
  it("ignores stale environment metadata even when all old names are set", () => {
    const expected = currentBuildInfo();
    for (const prefix of ["VITE", "ACKB"]) {
      vi.stubEnv(`${prefix}_APP_VERSION`, "1.0.1");
      vi.stubEnv(`${prefix}_COMMIT_SHA`, stale);
      vi.stubEnv(`${prefix}_BUILD_DATE`, "2000-01-01T00:00:00Z");
    }
    vi.stubEnv("ACKB_BUILD_GIT_SHA", stale);
    const info = currentBuildInfo();
    expect(info.version).toBe(expected.version);
    expect(info.commitSha).toBe(expected.commitSha);
    expect(info.buildDate).not.toBe("2000-01-01T00:00:00Z");
  });
});
