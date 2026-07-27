import { spawnSync } from "node:child_process";
import process, { stderr, stdout } from "node:process";

const log = (message) => { stdout.write(`${message}\n`); };
const warn = (message) => { stderr.write(`${message}\n`); };

const allowedAdvisories = new Set([
  // This application is a client-only Vite SPA and does not enable React Router
  // RSC mode or server actions, so the affected execution path is absent.
  "https://github.com/advisories/GHSA-qwww-vcr4-c8h2",
]);
const severityRank = {
  info: 0,
  low: 1,
  moderate: 2,
  high: 3,
  critical: 4,
};
const npm = process.platform === "win32" ? "npm.cmd" : "npm";
const result = spawnSync(npm, ["audit", "--json"], {
  encoding: "utf8",
  maxBuffer: 16 * 1024 * 1024,
});

if (result.error !== undefined || result.stdout.trim() === "") {
  warn("npm audit could not produce a report.");
  if (result.stderr.trim() !== "") warn(result.stderr.trim());
  process.exit(1);
}

let report;
try {
  report = JSON.parse(result.stdout);
} catch {
  warn("npm audit returned invalid JSON.");
  process.exit(1);
}

if (report.error !== undefined || report.vulnerabilities === undefined) {
  warn("npm audit returned an error instead of a vulnerability report.");
  process.exit(1);
}

const advisoryUrls = (name, seen = new Set()) => {
  if (seen.has(name)) return new Set();
  seen.add(name);
  const vulnerability = report.vulnerabilities[name];
  if (vulnerability === undefined) return new Set();

  const urls = new Set();
  for (const cause of vulnerability.via) {
    if (typeof cause === "string") {
      for (const url of advisoryUrls(cause, seen)) urls.add(url);
    } else if (typeof cause.url === "string") {
      urls.add(cause.url);
    }
  }
  return urls;
};

const findings = Object.entries(report.vulnerabilities)
  .filter(([, vulnerability]) =>
    severityRank[vulnerability.severity] >= severityRank.high)
  .map(([name, vulnerability]) => ({
    name,
    severity: vulnerability.severity,
    urls: advisoryUrls(name),
  }));
const blocked = findings.filter(({ urls }) =>
  urls.size === 0 || [...urls].some((url) => !allowedAdvisories.has(url)));

if (blocked.length > 0) {
  warn("Unaccepted high or critical npm audit findings:");
  for (const finding of blocked) {
    warn(
      `- ${finding.name} (${finding.severity}): ${[...finding.urls].join(", ") || "unknown advisory"}`,
    );
  }
  process.exit(1);
}

const accepted = new Set(
  findings.flatMap(({ urls }) => [...urls]),
);
if (accepted.size > 0) {
  warn(
    "Accepted npm audit advisory for an unused React Router RSC/server-action path:",
  );
  for (const url of accepted) warn(`- ${url}`);
} else {
  log("npm audit found no high or critical vulnerabilities.");
}
