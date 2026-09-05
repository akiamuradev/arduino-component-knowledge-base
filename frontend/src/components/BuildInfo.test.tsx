import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BUILD_INFO } from "../config/brand";
import { BuildInfo } from "./BuildInfo";

describe("build information", () => {
  it("shows the verified release commit and build date on the about page", () => {
    render(<BuildInfo />);

    expect(screen.getByText(BUILD_INFO.commitSha.slice(0, 8))).toBeVisible();
    expect(screen.getByText(BUILD_INFO.buildDate)).toBeVisible();
    expect(BUILD_INFO.commitSha).toMatch(/^[a-f0-9]{40}$/);
    expect(BUILD_INFO.buildDate).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  });

  it("shows the same commit beside the version in the footer", () => {
    render(<BuildInfo compact />);

    expect(screen.getByText(`v${BUILD_INFO.version} · ${BUILD_INFO.commitSha.slice(0, 8)}`)).toBeVisible();
  });
});
