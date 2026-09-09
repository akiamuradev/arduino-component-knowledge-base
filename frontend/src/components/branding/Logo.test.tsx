import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { LogoCompact, LogoHeader, LogoPrimary } from "./Logo";
import { HeroBoardIllustration } from "./HeroBoardIllustration";

describe("vector branding", () => {
  it("draws ACKB with paths rather than fonts or embedded images", () => {
    const { container } = render(<><LogoHeader /><LogoPrimary monochrome /><LogoCompact /></>);
    expect(container.querySelectorAll("svg")).toHaveLength(3);
    expect(container.querySelectorAll("svg path")).toHaveLength(6);
    expect(container.querySelector("svg text, image, img")).toBeNull();
    expect(container.querySelector(".ackb-logo--mono")).toBeInTheDocument();
    expect(container).toHaveTextContent("База компонентов Arduino");
  });
  it("draws the board as reusable vector assemblies with unique paint IDs", () => {
    const { container } = render(<><HeroBoardIllustration /><HeroBoardIllustration /></>);
    const ids = [...container.querySelectorAll("[id]")].map((node) => node.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(container.querySelector("image, img")).toBeNull();
    expect(container).toHaveTextContent("USB TYPE-B");
    expect(container).toHaveTextContent("ATmega328P / MCU");
  });
});
