import { useEffect, useRef } from "react";

import { HeroBoardIllustration } from "./branding/HeroBoardIllustration";

/** Decorative board: pointer work is coalesced into one frame, never a perpetual loop. */
export function HardwareBoard() {
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = rootRef.current;
    if (node === null) return;
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    let frame: number | null = null;
    let x = 0;
    let y = 0;
    const render = () => {
      frame = null;
      node.style.setProperty("--board-rx", `${String(-y * 4)}deg`);
      node.style.setProperty("--board-ry", `${String(x * 4)}deg`);
      node.style.setProperty("--board-hx", `${String(50 + x * 25)}%`);
      node.style.setProperty("--board-hy", `${String(50 + y * 25)}%`);
      node.style.setProperty("--board-sx", `${String(-x * 8)}px`);
      node.style.setProperty("--board-sy", `${String(14 - y * 4)}px`);
      node.style.setProperty("--board-px", `${String(x * 3)}px`);
      node.style.setProperty("--board-py", `${String(y * 3)}px`);
      node.style.setProperty("--board-trace-alpha", String(0.3 + Math.hypot(x, y) * 0.12));
    };
    const reset = () => {
      if (frame !== null) cancelAnimationFrame(frame);
      x = 0;
      y = 0;
      render();
    };
    const updatePreference = () => {
      node.dataset.motion = media.matches ? "static" : "interactive";
      reset();
    };
    const move = (event: PointerEvent) => {
      if (media.matches || event.pointerType === "touch") return;
      const bounds = node.getBoundingClientRect();
      if (bounds.width === 0 || bounds.height === 0) return;
      x = Math.max(-1, Math.min(1, 2 * (event.clientX - bounds.left) / bounds.width - 1));
      y = Math.max(-1, Math.min(1, 2 * (event.clientY - bounds.top) / bounds.height - 1));
      frame ??= requestAnimationFrame(render);
    };
    updatePreference();
    node.addEventListener("pointermove", move, { passive: true });
    node.addEventListener("pointerleave", reset);
    node.addEventListener("pointercancel", reset);
    media.addEventListener("change", updatePreference);
    return () => {
      if (frame !== null) cancelAnimationFrame(frame);
      node.removeEventListener("pointermove", move);
      node.removeEventListener("pointerleave", reset);
      node.removeEventListener("pointercancel", reset);
      media.removeEventListener("change", updatePreference);
    };
  }, []);

  return (
    <div className="hardware-board" ref={rootRef} aria-hidden="true">
      <div className="hardware-board__pcb"><HeroBoardIllustration /><span className="hardware-board__highlight" /></div>
    </div>
  );
}
