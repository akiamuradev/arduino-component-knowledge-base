import { type ThemePreference, useTheme } from "../theme/context";

const options: { value: ThemePreference; label: string; symbol: string }[] = [
  { value: "light", label: "Светлая тема", symbol: "☼" },
  { value: "dark", label: "Тёмная тема", symbol: "☾" },
  { value: "system", label: "Системная тема", symbol: "◐" },
];

export function ThemeToggle() {
  const { preference, setPreference } = useTheme();
  return (
    <div className="theme-toggle" role="group" aria-label="Цветовая тема">
      {options.map((option) => (
        <button
          aria-label={option.label}
          aria-pressed={preference === option.value}
          key={option.value}
          onClick={() => {
            setPreference(option.value);
          }}
          title={option.label}
          type="button"
        >
          <span aria-hidden="true">{option.symbol}</span>
        </button>
      ))}
    </div>
  );
}
