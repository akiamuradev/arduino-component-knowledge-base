import { fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HardwareBoard } from "./HardwareBoard";

afterEach(() => { vi.restoreAllMocks(); });

describe("hardware board", () => {
  it("coalesces pointer events, bounds the tilt and cancels pending work", () => {
    const raf = vi.spyOn(window, "requestAnimationFrame").mockReturnValue(42);
    const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => undefined);
    const { container, unmount } = render(<HardwareBoard />);
    const board = container.querySelector<HTMLElement>(".hardware-board");
    if (board === null) throw new Error("Missing board");
    vi.spyOn(board, "getBoundingClientRect").mockReturnValue(new DOMRect(0, 0, 400, 240));
    fireEvent(board, new MouseEvent("pointermove", { clientX: 450, clientY: -30 }));
    fireEvent(board, new MouseEvent("pointermove", { clientX: 450, clientY: -30 }));
    expect(raf).toHaveBeenCalledTimes(1);
    raf.mock.calls[0]?.[0](0);
    expect(board.style.getPropertyValue("--board-ry")).toBe("4deg");
    expect(board.style.getPropertyValue("--board-rx")).toBe("4deg");
    fireEvent.pointerLeave(board);
    expect(board.style.getPropertyValue("--board-ry")).toBe("0deg");
    fireEvent(board, new MouseEvent("pointermove", { clientX: 300, clientY: 40 }));
    unmount();
    expect(cancel).toHaveBeenCalledWith(42);
  });

  it("keeps reduced-motion decoration static", () => {
    vi.spyOn(window, "matchMedia").mockReturnValue({
      matches: true, media: "(prefers-reduced-motion: reduce)", onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(),
      removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    });
    const raf = vi.spyOn(window, "requestAnimationFrame");
    const { container } = render(<HardwareBoard />);
    const board = container.querySelector<HTMLElement>(".hardware-board");
    if (board === null) throw new Error("Missing board");
    fireEvent(board, new MouseEvent("pointermove", { clientX: 300, clientY: 40 }));
    expect(board).toHaveAttribute("data-motion", "static");
    expect(board.style.getPropertyValue("--board-ry")).toBe("0deg");
    expect(raf).not.toHaveBeenCalled();
  });
});
