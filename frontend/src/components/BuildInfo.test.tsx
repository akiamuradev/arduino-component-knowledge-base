import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BUILD_INFO } from "../config/brand";
import { BuildInfo } from "./BuildInfo";

describe("build information", () => {
  it("shows the verified release commit and build date on the about page", () => {
    render(<BuildInfo />);

    expect(screen.getByText("c720b265")).toBeVisible();
    expect(screen.getByText("2026-09-04T19:49:43Z")).toBeVisible();
    expect(BUILD_INFO.commitSha).toBe("c720b265dfac291370a38b83daa1de97256a9b3d");
  });

  it("shows the same commit beside the version in the footer", () => {
    render(<BuildInfo compact />);

    expect(screen.getByText("v1.0.0 · c720b265")).toBeVisible();
  });
});
