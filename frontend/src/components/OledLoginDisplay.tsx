import { type CSSProperties, type PointerEvent as ReactPointerEvent, useEffect, useRef } from "react";

import { GraffitiAccentBlob } from "./GraffitiAccentBlob";

export type OledState =
  | "idle"
  | "student_selected"
  | "admin_selected"
  | "submitting"
  | "success"
  | "error";

interface MotionValue {
  x: number;
  y: number;
  lift: number;
  scale: number;
}

const oledText: Record<OledState, readonly string[]> = {
  idle: ["ARDUINO BASE", "SYSTEM READY", "", "SELECT ACCESS", "> STUDENT", "  ADMIN"],
  student_selected: ["ACCESS MODE", "STUDENT", "", "READY TO LEARN"],
  admin_selected: ["ACCESS MODE", "ADMIN", "", "AUTH REQUIRED"],
  submitting: ["CHECKING...", "PLEASE WAIT"],
  success: ["ACCESS GRANTED", "WELCOME!"],
  error: ["ACCESS DENIED", "CHECK LOGIN"],
};

const INITIAL: MotionValue = { x: 0, y: 0, lift: 0, scale: 1 };

export function OledLoginDisplay({ state }: { state: OledState }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const target = useRef<MotionValue>({ ...INITIAL });
  const current = useRef<MotionValue>({ ...INITIAL });
  const velocity = useRef<MotionValue>({ x: 0, y: 0, lift: 0, scale: 0 });
  const frameId = useRef<number | null>(null);
  const bounds = useRef<DOMRect | null>(null);
  const reducedMotion = useRef(false);
  const pressed = useRef(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => {
      reducedMotion.current = media.matches;
      if (rootRef.current !== null) rootRef.current.dataset.motion = media.matches ? "static" : "interactive";
    };
    update();
    media.addEventListener("change", update);
    return () => {
      media.removeEventListener("change", update);
      if (frameId.current !== null) cancelAnimationFrame(frameId.current);
    };
  }, []);

  const renderMotion = () => {
    const node = rootRef.current;
    if (node === null) return;
    const value = current.current;
    const intensity = Math.min(1, Math.hypot(value.x, value.y));
    node.style.setProperty("--oled-rotate-x", `${String(2 + value.y * 6)}deg`);
    node.style.setProperty("--oled-rotate-y", `${String(-3 + value.x * 8)}deg`);
    node.style.setProperty("--oled-translate-x", `${String(value.x * 4)}px`);
    node.style.setProperty("--oled-translate-y", `${String(value.y * 3 - value.lift)}px`);
    node.style.setProperty("--oled-scale", String(value.scale));
    node.style.setProperty("--oled-highlight-x", `${String(50 + value.x * 28)}%`);
    node.style.setProperty("--oled-highlight-y", `${String(35 + value.y * 24)}%`);
    node.style.setProperty("--oled-highlight-opacity", String(0.025 + intensity * 0.13 + (pressed.current ? 0.06 : 0)));
    node.style.setProperty("--oled-highlight-angle", `${String(18 + value.x * 12)}deg`);
    node.style.setProperty("--oled-highlight-scale", String(1 + intensity * 0.08));
    node.style.setProperty("--oled-shadow-x", `${String(-value.x * 14)}px`);
    node.style.setProperty("--oled-shadow-y", `${String(18 + value.y * -5 + value.lift * 0.4)}px`);
    node.style.setProperty("--oled-shadow-blur", `${String(20 + value.lift * 1.4)}px`);
    node.style.setProperty("--oled-shadow-opacity", String(pressed.current ? 0.3 : 0.2));
    node.style.setProperty("--blob-x", `${String(value.x * 1.2)}px`);
    node.style.setProperty("--blob-y", `${String(value.y * 0.9)}px`);
  };

  const animate = () => {
    frameId.current = null;
    const keys: (keyof MotionValue)[] = ["x", "y", "lift", "scale"];
    let unsettled = false;
    for (const key of keys) {
      const delta = target.current[key] - current.current[key];
      velocity.current[key] = (velocity.current[key] + delta * 0.08) * 0.82;
      current.current[key] += velocity.current[key];
      if (Math.abs(delta) > 0.001 || Math.abs(velocity.current[key]) > 0.001) unsettled = true;
    }
    renderMotion();
    if (unsettled) frameId.current = requestAnimationFrame(animate);
  };

  const startAnimation = () => {
    if (reducedMotion.current || frameId.current !== null) return;
    frameId.current = requestAnimationFrame(animate);
  };

  const updatePointer = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (reducedMotion.current || event.pointerType === "touch") return;
    const rect = bounds.current ?? event.currentTarget.getBoundingClientRect();
    bounds.current = rect;
    target.current.x = Math.max(-1, Math.min(1, (event.clientX - (rect.left + rect.width / 2)) / (rect.width / 2)));
    target.current.y = Math.max(-1, Math.min(1, (event.clientY - (rect.top + rect.height / 2)) / (rect.height / 2)));
    target.current.lift = pressed.current ? 2 : 9;
    startAnimation();
  };

  const pointerEnter = (event: ReactPointerEvent<HTMLDivElement>) => {
    bounds.current = event.currentTarget.getBoundingClientRect();
    updatePointer(event);
  };
  const pointerLeave = () => {
    bounds.current = null;
    pressed.current = false;
    target.current = { ...INITIAL };
    startAnimation();
  };
  const pointerDown = () => {
    pressed.current = true;
    target.current.lift = 2;
    target.current.scale = 0.985;
    startAnimation();
  };
  const pointerUp = () => {
    pressed.current = false;
    target.current.lift = 9;
    target.current.scale = 1;
    startAnimation();
  };

  return (
    <div
      aria-hidden="true"
      className="oled-composition"
      data-oled-state={state}
      onPointerDown={pointerDown}
      onPointerEnter={pointerEnter}
      onPointerLeave={pointerLeave}
      onPointerMove={updatePointer}
      onPointerUp={pointerUp}
      ref={rootRef}
      style={{ "--oled-highlight-opacity": 0.025 } as CSSProperties}
    >
      <div className="oled-reactive-shadow" data-testid="oled-shadow" />
      <GraffitiAccentBlob />
      <div className="oled-board" data-testid="oled-board">
        <span className="oled-hole oled-hole--one" /><span className="oled-hole oled-hole--two" /><span className="oled-hole oled-hole--three" /><span className="oled-hole oled-hole--four" />
        <div className="oled-traces"><span /><span /><span /><span /></div>
        <div className="oled-screen-bezel">
          <div className="oled-glass">
            <pre className="oled-text">{oledText[state].join("\n")}</pre>
            <span className="oled-cursor" />
            <span className="oled-highlight" data-testid="oled-highlight" />
          </div>
        </div>
        <div className="oled-components"><span /><span /><span /><span /><span /></div>
        <div className="oled-pins">{["GND", "VCC", "SCL", "SDA"].map((pin) => <span key={pin}><i />{pin}</span>)}</div>
      </div>
    </div>
  );
}
