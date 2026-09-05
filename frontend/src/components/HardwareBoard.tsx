import { useEffect, useRef } from "react";

import { BrandSplat } from "./BrandSplat";

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
      <BrandSplat className="hardware-board__splat" size="17rem" opacity={0.28} variant="muted" loading="eager" />
      <div className="hardware-board__pcb">
        <svg viewBox="0 0 400 240" focusable="false">
          <path d="M35 20 H350 L378 48 V205 Q378 220 362 220 H35 Q20 220 20 205 V35 Q20 20 35 20Z" fill="#20392e" stroke="#526d55" strokeWidth="3" />
          <g className="hardware-board__traces">
            <path d="M62 48 H128 L155 75 V96 M74 190 H112 L158 146 M202 64 V43 H317 M240 103 H302 L325 80 H356 M242 126 H325 V191 M202 166 V196 H275 M61 120 H120 M276 185 V160 H244 M115 43 V65 H88 V94" />
            <circle cx="128" cy="48" r="3" /><circle cx="325" cy="126" r="3" /><circle cx="112" cy="190" r="3" />
          </g>
          <rect x="6" y="90" width="55" height="48" rx="4" fill="#909991" stroke="#2b312b" strokeWidth="4" />
          <rect x="4" y="100" width="20" height="28" rx="2" fill="#343b35" />
          <rect x="28" y="164" width="49" height="31" rx="3" fill="#121b17" stroke="#536050" strokeWidth="2" />
          <rect x="152" y="79" width="94" height="85" rx="3" fill="#111e18" stroke="#63705b" strokeWidth="2" />
          <g fill="#b6ac79">
            {Array.from({ length: 10 }, (_, index) => (
              <g key={index}><rect x={163 + index * 7} y="73" width="3" height="8" /><rect x={163 + index * 7} y="163" width="3" height="8" /></g>
            ))}
            {Array.from({ length: 12 }, (_, index) => (
              <g key={index}><rect x={91 + index * 20} y="25" width="11" height="12" rx="1" /><rect x={91 + index * 20} y="202" width="11" height="12" rx="1" /></g>
            ))}
          </g>
          <g fill="#aebca7" fontFamily="monospace" textAnchor="middle">
            <text x="200" y="118" fontSize="18">MCU</text><text x="200" y="142" fontSize="10">ACKB / UNO</text>
            <text x="272" y="55" fontSize="9">DIGITAL / GPIO</text><text x="273" y="191" fontSize="9">ANALOG / PWR</text>
          </g>
          <circle cx="321" cy="102" r="4" fill="var(--color-accent)" />
          <g fill="#121b17" stroke="#a3a77a" strokeWidth="3">
            <circle cx="38" cy="39" r="6" /><circle cx="358" cy="59" r="6" /><circle cx="38" cy="205" r="6" /><circle cx="359" cy="204" r="6" />
          </g>
          <g fill="#121b17" stroke="#798570"><rect x="290" y="116" width="26" height="10" rx="2" /><rect x="94" y="141" width="22" height="10" rx="2" /></g>
        </svg>
        <span className="hardware-board__highlight" />
      </div>
    </div>
  );
}
