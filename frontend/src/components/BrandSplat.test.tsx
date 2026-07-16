import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BrandSplat } from "./BrandSplat";

describe("brand splat", () => {
  it("is a configurable non-interactive decorative asset", () => {
    const { container } = render(
      <BrandSplat animated className="custom-splat" opacity={0.7} rotation={-7} size="18rem" variant="glow" />,
    );
    const image = container.querySelector("img");
    expect(image).toHaveAttribute("alt", "");
    expect(image).toHaveAttribute("aria-hidden", "true");
    expect(image).toHaveAttribute("draggable", "false");
    expect(image).toHaveClass("brand-splat", "brand-splat--glow", "brand-splat--animated", "custom-splat");
    expect(image?.style.getPropertyValue("--splat-size")).toBe("18rem");
    expect(image?.style.getPropertyValue("--splat-opacity")).toBe("0.7");
    expect(image?.style.getPropertyValue("--splat-rotation")).toBe("-7deg");
  });
});
