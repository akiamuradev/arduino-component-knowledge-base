import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { stdout } from "node:process";
import { execFileSync } from "node:child_process";

const root = resolve(import.meta.dirname, "..");
const indexPath = resolve(root, "dist", "index.html");
if (!existsSync(indexPath)) {
  throw new Error("frontend dist/index.html is missing; run npm run build first");
}

const html = readFileSync(indexPath, "utf8");
const info = JSON.parse(readFileSync(resolve(root, "dist/build-info.json"), "utf8"));
const version = JSON.parse(readFileSync(resolve(root, "package.json"), "utf8")).version;
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
if (info.version !== version || info.commitSha !== commit ||
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/.test(info.buildDate) ||
    !Number.isFinite(Date.parse(info.buildDate))) {
  throw new Error("Frontend build provenance differs from project metadata / actual Git HEAD");
}
for (const publicAsset of ["theme-init.js", "manifest.webmanifest", "LICENCE.txt"]) {
  if (!existsSync(resolve(root, "dist", publicAsset))) {
    throw new Error(`frontend public asset is missing: ${publicAsset}`);
  }
}
if (readFileSync(resolve(root, "dist", "LICENCE.txt"), "utf8") !== readFileSync(resolve(root, "..", "LICENCE"), "utf8")) {
  throw new Error("frontend license differs from the project license");
}
if (!html.includes("theme-init.js") || !html.includes("manifest.webmanifest")) {
  throw new Error("frontend entry point is missing theme bootstrap or manifest");
}
if (!html.includes('content="akiamuradev"')) {
  throw new Error("frontend entry point is missing product authorship");
}
const assetMatches = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+)"/g)];
if (assetMatches.length === 0) {
  throw new Error("frontend build does not reference any bundled assets");
}
for (const match of assetMatches) {
  const asset = match[1];
  if (asset === undefined || !existsSync(resolve(root, "dist", asset.slice(1)))) {
    throw new Error(`missing bundled asset: ${asset ?? "unknown"}`);
  }
}
const bundledAssets = readdirSync(resolve(root, "dist", "assets"));
if (bundledAssets.some((asset) => asset.startsWith("green-splat-"))) {
  throw new Error("frontend build contains retired branding");
}
for (const asset of ["favicon.svg", "branding/ackb-primary.svg", "branding/ackb-monochrome.svg"]) {
  if (!existsSync(resolve(root, "dist", asset))) throw new Error(`missing brand asset: ${asset}`);
}
if (/AKIA[0-9A-Z]{16}|BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY/.test(html)) {
  throw new Error("secret-like material found in frontend entry point");
}
stdout.write("Frontend distribution smoke test passed.\n");
