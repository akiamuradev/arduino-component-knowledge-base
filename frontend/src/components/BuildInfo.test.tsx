import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BUILD_INFO } from "../config/brand";
import { BuildInfo } from "./BuildInfo";

describe("build information", () => {
  it("shows the verified release commit and build date on the about page", () => {
    render(<BuildInfo />);

    expect(screen.getByText("9bbcdac2")).toBeVisible();
    expect(screen.getByText("2026-09-04T19:39:16Z")).toBeVisible();
    expect(BUILD_INFO.commitSha).toBe("9bbcdac2983a4c96566c8dccb28454759d59f371");
  });

  it("shows the same commit beside the version in the footer", () => {
    render(<BuildInfo compact />);

    expect(screen.getByText("v1.0.0 · 9bbcdac2")).toBeVisible();
  });
});
