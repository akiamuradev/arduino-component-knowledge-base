import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type OledState, OledLoginDisplay } from "./OledLoginDisplay";

describe("OLED login display", () => {
  it.each<[OledState, string]>([
    ["idle", "SYSTEM READY"],
    ["student_selected", "STUDENT"],
    ["admin_selected", "ADMIN"],
    ["submitting", "CHECKING"],
    ["success", "ACCESS GRANTED"],
    ["error", "ACCESS DENIED"],
  ])("renders %s auth state", (state, text) => {
    const view = render(<OledLoginDisplay state={state} />);
    expect(view.container).toHaveTextContent(text);
    expect(view.container.firstElementChild).toHaveAttribute("aria-hidden", "true");
  });

  it("updates tilt, highlight and shadow through one animation loop, then returns", () => {
    const frames = new Map<number, FrameRequestCallback>();
    let nextFrame = 0;
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      nextFrame += 1;
      frames.set(nextFrame, callback);
      return nextFrame;
    }));
    const cancel = vi.fn((id: number) => { frames.delete(id); });
    vi.stubGlobal("cancelAnimationFrame", cancel);
    const view = render(<OledLoginDisplay state="idle" />);
    const root = view.container.firstElementChild as HTMLElement;
    root.getBoundingClientRect = vi.fn(() => ({ x: 0, y: 0, left: 0, top: 0, right: 400, bottom: 300, width: 400, height: 300, toJSON: vi.fn() }));
    fireEvent.pointerEnter(root, { clientX: 390, clientY: 20, pointerType: "mouse" });
    fireEvent.pointerMove(root, { clientX: 390, clientY: 20, pointerType: "mouse" });
    for (let index = 0; index < 12; index += 1) {
      const entry = frames.entries().next().value;
      if (entry === undefined) break;
      frames.delete(entry[0]);
      entry[1](index * 16);
    }
    expect(root.style.getPropertyValue("--oled-highlight-x")).not.toBe("50%");
    expect(root.style.getPropertyValue("--oled-shadow-x")).not.toBe("0px");
    const board = view.getByTestId("oled-board");
    fireEvent.pointerDown(root);
    expect(root.dataset.oledState).toBe("idle");
    expect(board).toBeInTheDocument();
    fireEvent.pointerLeave(root);
    view.unmount();
    expect(cancel).toHaveBeenCalled();
  });

  it("disables pointer animation for reduced motion", () => {
    vi.mocked(window.matchMedia).mockImplementation((query: string) => ({
      matches: query.includes("reduced-motion"), media: query, onchange: null,
      addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(),
      removeListener: vi.fn(), dispatchEvent: vi.fn(),
    }));
    const requestFrame = vi.fn();
    vi.stubGlobal("requestAnimationFrame", requestFrame);
    const view = render(<OledLoginDisplay state="idle" />);
    const root = view.container.firstElementChild as HTMLElement;
    fireEvent.pointerMove(root, { clientX: 20, clientY: 20, pointerType: "mouse" });
    expect(root.dataset.motion).toBe("static");
    expect(requestFrame).not.toHaveBeenCalled();
  });

  it("keeps the deterministic lime blob behind the board", () => {
    const view = render(<OledLoginDisplay state="idle" />);
    const blob = view.getByTestId("graffiti-blob");
    const dots = view.getByTestId("graffiti-dots");
    const board = view.getByTestId("oled-board");
    expect(blob.compareDocumentPosition(board) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(dots.querySelectorAll("circle")).toHaveLength(40);
    expect(blob).toHaveClass("graffiti-blob");
  });
});
