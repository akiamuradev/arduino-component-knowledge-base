import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

declare const __ACKB_LICENSE_TEXT__: string;

it("embeds the unchanged canonical repository license, not a separately edited legal body", () => {
  const canonical = readFileSync("../LICENCE", "utf8");
  const publicCopy = readFileSync("public/LICENCE.txt", "utf8");
  expect(publicCopy).toBe(canonical);
  expect(__ACKB_LICENSE_TEXT__).toBe(canonical);
});
