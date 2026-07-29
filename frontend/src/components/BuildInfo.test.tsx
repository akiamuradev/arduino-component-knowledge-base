import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BUILD_INFO } from "../config/brand";
import { BuildInfo } from "./BuildInfo";

describe("build information", () => {
  it("shows the verified release commit and build date on the about page", () => {
    render(<BuildInfo />);

    expect(screen.getByText("899baaaa")).toBeVisible();
    expect(screen.getByText("2026-07-29T17:23:09Z")).toBeVisible();
    expect(BUILD_INFO.commitSha).toBe("899baaaa68dccbd0d5d42e54f8be772696c260e5");
  });

  it("shows the same commit beside the version in the footer", () => {
    render(<BuildInfo compact />);

    expect(screen.getByText("v1.0.0 · 899baaaa")).toBeVisible();
  });
});
