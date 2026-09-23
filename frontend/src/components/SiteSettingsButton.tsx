import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { ACCENT_PRESETS, onAccent, type AccentPreset } from "../theme/colors";
import { useTheme } from "../theme/context";
import { MAX_SAVED_ACCENTS } from "../theme/preferences";
import { CustomAccentPicker } from "./CustomAccentPicker";
import "./site-settings.css";

function SiteSettingsPanel({ anchor, onClose }: { anchor: RefObject<HTMLButtonElement | null>; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const lastControl = useRef<HTMLAnchorElement>(null);
  const id = useId();
  const { preference, setPreference, accent, accentColor, setAccentPreset, setCustomAccent,
    savedAccents, saveCurrentAccent, removeSavedAccent } = useTheme();
  const [validDraft, setValidDraft] = useState(true);
  const [pickerReset, setPickerReset] = useState(0);
  const customChoice = useRef<HTMLInputElement>(null);
  useLayoutEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const position = () => {
      const rect = anchor.current?.getBoundingClientRect();
      const width = Math.min(384, window.innerWidth - 16);
      const left = Math.max(8, Math.min((rect?.right ?? window.innerWidth - 8) - width, window.innerWidth - width - 8));
      const top = window.innerWidth <= 600 ? 8 : Math.max(8, Math.min((rect?.bottom ?? 0) + 8, window.innerHeight - 200));
      element.style.left = `${String(left)}px`;
      element.style.top = `${String(top)}px`;
      element.style.maxHeight = `${String(Math.max(100, window.innerHeight - top - 8))}px`;
    };
    position();
    element.showModal();
    close.current?.focus();
    window.addEventListener("resize", position);
    return () => { window.removeEventListener("resize", position); element.close(); };
  }, [anchor]);
  // Native dialog handles focus containment; return focus explicitly to its trigger.
  useEffect(() => {
    const trigger = anchor.current;
    return () => { trigger?.focus(); };
  }, [anchor]);
  return createPortal(<dialog ref={dialog} className="site-settings-panel" aria-labelledby={`${id}-title`}
    onCancel={(event) => { event.preventDefault(); onClose(); }}
    onKeyDown={(event) => {
      // Keep Tab at the dialog boundaries instead of sending it to browser chrome.
      // Native radio groups retain their normal arrow-key / single-tab-stop behavior.
      if (event.key !== "Tab") return;
      if (event.shiftKey && document.activeElement === close.current) {
        event.preventDefault(); lastControl.current?.focus();
      } else if (!event.shiftKey && document.activeElement === lastControl.current) {
        event.preventDefault(); close.current?.focus();
      }
    }}
    onClick={(event) => {
      if (event.target !== event.currentTarget) return;
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }}>
    <div className="site-settings-panel__header">
      <h2 id={`${id}-title`}>Настройки сайта</h2>
      <button ref={close} type="button" className="site-settings-close" aria-label="Закрыть настройки сайта" onClick={onClose}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
    </div>
    <fieldset className="settings-section"><legend>Тема</legend>
      <div className="settings-themes">{([
        ["light", "Светлое"], ["dark", "Тёмное"], ["system", "Как на устройстве"],
      ] as const).map(([value, label]) => <label key={value}>
        <input type="radio" name={`${id}-theme`} value={value} checked={preference === value} onChange={() => { setPreference(value); }} />
        <span>{label}</span>
      </label>)}</div>
    </fieldset>
    <fieldset className="settings-section"><legend>Акцентный цвет</legend>
      <div className="settings-swatches">{Object.entries(ACCENT_PRESETS).map(([key, preset]) => {
        const selected = accent.type === "preset" && accent.value === key;
        return <label key={key} title={`${preset.label} ${preset.hex}`} className="settings-swatch">
          <input type="radio" name={`${id}-accent`} aria-label={preset.label} checked={selected}
            onChange={() => { setAccentPreset(key as AccentPreset); }} />
          <span style={{ background: preset.hex, color: onAccent(preset.hex) }} aria-hidden="true">
            {selected && <svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg>}
          </span>
        </label>;
      })}</div>
      <label className="settings-custom-choice"><input ref={customChoice} type="radio" name={`${id}-accent`} checked={accent.type === "custom"}
        onChange={() => { setCustomAccent(accentColor); }} /><span>Свой цвет</span></label>
      {accent.type === "custom" && <>
        <CustomAccentPicker key={pickerReset} color={accentColor} onChange={setCustomAccent} onValidityChange={setValidDraft} />
        <button type="button" className="button button--quiet" disabled={!validDraft || savedAccents.includes(accentColor) || savedAccents.length >= MAX_SAVED_ACCENTS}
          onClick={saveCurrentAccent}>Сохранить цвет</button>
      </>}
      {savedAccents.length >= MAX_SAVED_ACCENTS && <p className="settings-hint">Можно сохранить до 12 цветов.</p>}
      {savedAccents.length > 0 && <section className="settings-saved" aria-labelledby={`${id}-saved-title`}>
        <h3 id={`${id}-saved-title`}>Мои цвета</h3>
        <div className="settings-swatches">{savedAccents.map((hex) => {
          const selected = accent.type === "custom" && accentColor === hex;
          return <div className="settings-saved__item" key={hex}>
            <button type="button" className="settings-swatch" aria-label={hex} title={hex} aria-pressed={selected}
              onClick={() => { setCustomAccent(hex); setPickerReset((old) => old + 1); }}>
              <span style={{ background: hex, color: onAccent(hex) }} aria-hidden="true">
                {selected && <svg viewBox="0 0 24 24"><path d="m5 12 4 4L19 6" /></svg>}
              </span>
            </button>
            <button type="button" className="settings-saved__remove" aria-label={`Удалить цвет ${hex}`} title={`Удалить цвет ${hex}`}
              onClick={(event) => {
                // Deleting the focused control must not leave focus on the page body.
                const item = event.currentTarget.parentElement;
                const neighbor = item?.nextElementSibling ?? item?.previousElementSibling;
                const next = neighbor?.querySelector<HTMLButtonElement>("button") ?? customChoice.current;
                removeSavedAccent(hex);
                next?.focus();
              }}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
            </button>
          </div>;
        })}</div>
      </section>}
    </fieldset>
    <section className="settings-preview" aria-label="Предпросмотр">
      <h3>Предпросмотр</h3>
      <div><button type="button" className="button button--accent">Кнопка</button>
        <a ref={lastControl} href="#appearance-preview" onClick={(event) => { event.preventDefault(); }}>Ссылка</a>
        <span className="settings-preview__selected">✓ Выбрано</span></div>
    </section>
  </dialog>, document.body);
}

export function SiteSettingsButton() {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const onClose = useCallback(() => { setOpen(false); }, []);
  return <>
    <button ref={trigger} type="button" className="site-settings-trigger" title="Настройки сайта"
      aria-label="Настройки сайта" aria-haspopup="dialog" aria-expanded={open} onClick={() => { setOpen(true); }}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 3-.6 2.1-1.8 1-2.1-.5-2 3.5L4 10.7v2.6l-1.5 1.6 2 3.5 2.1-.5 1.8 1L9 21h4l.6-2.1 1.8-1 2.1.5 2-3.5-1.5-1.6v-2.6l1.5-1.6-2-3.5-2.1.5-1.8-1L13 3Z" /><circle cx="11" cy="12" r="3" /></svg>
    </button>
    {open && <SiteSettingsPanel anchor={trigger} onClose={onClose} />}
  </>;
}
