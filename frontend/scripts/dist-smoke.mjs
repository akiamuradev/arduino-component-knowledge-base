import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { stdout } from "node:process";

const root = resolve(import.meta.dirname, "..");
const indexPath = resolve(root, "dist", "index.html");
if (!existsSync(indexPath)) {
  throw new Error("frontend dist/index.html is missing; run npm run build first");
}

const html = readFileSync(indexPath, "utf8");
for (const publicAsset of ["theme-init.js", "manifest.webmanifest"]) {
  if (!existsSync(resolve(root, "dist", publicAsset))) {
    throw new Error(`frontend public asset is missing: ${publicAsset}`);
  }
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
if (/AKIA[0-9A-Z]{16}|BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY/.test(html)) {
  throw new Error("secret-like material found in frontend entry point");
}
stdout.write("Frontend distribution smoke test passed.\n");
