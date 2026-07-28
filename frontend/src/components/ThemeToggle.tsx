import {
  type FocusEvent,
  type KeyboardEvent,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { type ThemePreference, useTheme } from "../theme/context";

interface ThemeOption {
  value: ThemePreference;
  label: string;
}

const OPTIONS: readonly ThemeOption[] = [
  { value: "light", label: "Светлое" },
  { value: "dark", label: "Тёмное" },
  { value: "system", label: "Как на устройстве" },
];

function ThemeIcon({
  name,
}: {
  name: ThemePreference | "check";
}) {
  if (name === "light") {
    return (
      <svg aria-hidden="true" className="theme-icon" viewBox="0 0 24 24">
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42" />
      </svg>
    );
  }
  if (name === "dark") {
    return (
      <svg aria-hidden="true" className="theme-icon" viewBox="0 0 24 24">
        <path d="M20.3 15.4A8.5 8.5 0 0 1 8.6 3.7 8.5 8.5 0 1 0 20.3 15.4Z" />
      </svg>
    );
  }
  if (name === "system") {
    return (
      <svg aria-hidden="true" className="theme-icon" viewBox="0 0 24 24">
        <rect height="13" rx="2" width="18" x="3" y="4" />
        <path d="M8 21h8M12 17v4" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className="theme-icon theme-icon--check" viewBox="0 0 24 24">
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const pendingFocus = useRef<number | null>(null);
  const menuId = useId();
  const activeLabel =
    OPTIONS.find((option) => option.value === preference)?.label ?? "Как на устройстве";

  useEffect(() => {
    if (!open || pendingFocus.current === null) return;
    optionRefs.current[pendingFocus.current]?.focus();
    pendingFocus.current = null;
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
    };
  }, [open]);

  const openAndFocus = (index: number) => {
    if (open) {
      optionRefs.current[index]?.focus();
      return;
    }
    pendingFocus.current = index;
    setOpen(true);
  };

  const closeAndFocusTrigger = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const choose = (option: ThemeOption) => {
    setPreference(option.value);
    closeAndFocusTrigger();
  };

  const handleTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      openAndFocus(0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAndFocus(OPTIONS.length - 1);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      closeAndFocusTrigger();
    }
  };

  const handleMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = optionRefs.current.findIndex(
      (option) => option === document.activeElement,
    );
    let nextIndex: number | null = null;
    if (event.key === "ArrowDown") {
      nextIndex = (currentIndex + 1) % OPTIONS.length;
    } else if (event.key === "ArrowUp") {
      nextIndex = (currentIndex - 1 + OPTIONS.length) % OPTIONS.length;
    } else if (event.key === "Home") {
      nextIndex = 0;
    } else if (event.key === "End") {
      nextIndex = OPTIONS.length - 1;
    } else if (event.key === "Escape") {
      event.preventDefault();
      closeAndFocusTrigger();
      return;
    } else if (event.key === "Tab") {
      setOpen(false);
      return;
    }
    if (nextIndex !== null) {
      event.preventDefault();
      optionRefs.current[nextIndex]?.focus();
    }
  };

  const handleBlur = (event: FocusEvent<HTMLDivElement>) => {
    if (!rootRef.current?.contains(event.relatedTarget)) setOpen(false);
  };

  return (
    <div className="theme-toggle" onBlur={handleBlur} ref={rootRef}>
      <button
        aria-controls={menuId}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`Оформление: ${activeLabel}. Открыть меню`}
        className="theme-toggle__trigger"
        onClick={() => {
          if (open) {
            setOpen(false);
          } else {
            const activeIndex = OPTIONS.findIndex((option) => option.value === preference);
            openAndFocus(activeIndex === -1 ? 0 : activeIndex);
          }
        }}
        onKeyDown={handleTriggerKeyDown}
        ref={triggerRef}
        title="Настроить оформление"
        type="button"
      >
        <ThemeIcon name={preference} />
      </button>
      {open ? (
        <div
          aria-label="Выбор оформления"
          className="theme-toggle__menu"
          id={menuId}
          onKeyDown={handleMenuKeyDown}
          role="menu"
        >
          <p>Оформление</p>
          {OPTIONS.map((option, index) => {
            const active = preference === option.value;
            return (
              <button
                aria-checked={active}
                className={active ? "theme-toggle__option active" : "theme-toggle__option"}
                key={option.value}
                onClick={() => {
                  choose(option);
                }}
                ref={(element) => {
                  optionRefs.current[index] = element;
                }}
                role="menuitemradio"
                type="button"
              >
                <ThemeIcon name={option.value} />
                <span>{option.label}</span>
                {active ? <ThemeIcon name="check" /> : <span aria-hidden="true" />}
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
