import { useCallback, useEffect, useId, useState, type PointerEvent } from "react";
import { clamp, hexToHsv, hexToRgb, hsvToHex, normalizeHex, rgbToHex, type Hsv } from "../theme/colors";

function ColorField({ label, value, numeric = false, onValid, onValidityChange }: {
  label: string; value: string; numeric?: boolean; onValid: (value: string) => void;
  onValidityChange: (field: string, valid: boolean) => void;
}) {
  const id = useId();
  const [previous, setPrevious] = useState(value);
  const [draft, setDraft] = useState(value);
  if (previous !== value) { setPrevious(value); setDraft(value); }
  const valid = numeric ? /^\d{1,3}$/.test(draft) && Number(draft) <= 255 : normalizeHex(draft) !== null;
  useEffect(() => { onValidityChange(label, valid); }, [label, valid, onValidityChange]);
  return <div className="settings-color-field">
    <label htmlFor={id}>{label}</label>
    <input id={id} type="text" inputMode={numeric ? "numeric" : "text"} value={draft}
      spellCheck={false} autoComplete="off" aria-invalid={!valid} aria-describedby={!valid ? `${id}-error` : undefined}
      onChange={(event) => {
        const next = event.target.value;
        setDraft(next);
        if (numeric ? /^\d{1,3}$/.test(next) && Number(next) <= 255 : normalizeHex(next)) onValid(next);
      }} />
    {!valid && <small id={`${id}-error`}>{numeric ? "От 0 до 255" : "Шесть HEX-цифр, например #B45CFF"}</small>}
  </div>;
}

export function CustomAccentPicker({ color, onChange, onValidityChange }: {
  color: string; onChange: (color: string) => void; onValidityChange: (valid: boolean) => void;
}) {
  const [invalidFields, setInvalidFields] = useState<Set<string>>(() => new Set());
  const fieldValidity = useCallback((field: string, valid: boolean) => {
    setInvalidFields((old) => {
      if (old.has(field) === !valid) return old;
      const next = new Set(old);
      if (valid) next.delete(field); else next.add(field);
      return next;
    });
  }, []);
  useEffect(() => { onValidityChange(invalidFields.size === 0); }, [invalidFields, onValidityChange]);
  const [previous, setPrevious] = useState(color);
  const [hsv, setHsv] = useState(() => hexToHsv(color));
  // Keep hue/saturation at black (and hue at gray), where RGB cannot encode them.
  if (previous !== color) {
    setPrevious(color);
    const next = hexToHsv(color);
    setHsv({ ...next, h: next.s === 0 ? hsv.h : next.h, s: next.v === 0 ? hsv.s : next.s });
  }
  const rgb = hexToRgb(color);
  const update = (next: Hsv) => {
    const hex = hsvToHex(next);
    setHsv(next);
    setPrevious(hex);
    onChange(hex);
  };
  const pick = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left - rect.width / 2;
    const y = event.clientY - rect.top - rect.height / 2;
    update({ ...hsv, h: (Math.atan2(y, x) * 180 / Math.PI + 360) % 360,
      s: clamp(Math.hypot(x, y) / (rect.width / 2)) });
  };
  const angle = hsv.h * Math.PI / 180;
  return <div className="settings-custom-color">
    <p className="settings-hint">Выберите цвет на круге или введите HEX / RGB с клавиатуры.</p>
    <div className="settings-color-wheel" aria-hidden="true"
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        pick(event);
      }} onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) pick(event); }}>
      <span className="settings-color-wheel__shade" style={{ opacity: 1 - hsv.v }} />
      <span className="settings-color-wheel__marker" style={{ left: `${String(50 + Math.cos(angle) * hsv.s * 50)}%`, top: `${String(50 + Math.sin(angle) * hsv.s * 50)}%` }} />
    </div>
    <label className="settings-brightness"><span>Яркость</span>
      <input type="range" aria-label="Яркость" aria-valuetext={`${String(Math.round(hsv.v * 100))}%`} min="0" max="100" step="1" value={Math.round(hsv.v * 100)}
        onChange={(event) => { update({ ...hsv, v: Number(event.target.value) / 100 }); }} />
      <output>{Math.round(hsv.v * 100)}%</output>
    </label>
    <ColorField label="HEX" value={color} onValid={onChange} onValidityChange={fieldValidity} />
    <div className="settings-rgb">
      {([['r', 'Красный (R)'], ['g', 'Зелёный (G)'], ['b', 'Синий (B)']] as const).map(([channel, label]) =>
        <ColorField key={channel} label={label} numeric value={String(rgb[channel])} onValidityChange={fieldValidity}
          onValid={(value) => { onChange(rgbToHex({ ...rgb, [channel]: Number(value) })); }} />)}
    </div>
  </div>;
}
