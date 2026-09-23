(function () {
  try {
    var preference = window.localStorage.getItem("ackb-theme");
    try {
      var saved = JSON.parse(window.localStorage.getItem("ackb-ui-preferences"));
      var accent = saved && saved.accent;
      var validAccent = accent && ((accent.type === "preset" && ["green", "cyan", "blue", "violet", "orange"].includes(accent.value))
        || (accent.type === "custom" && typeof accent.value === "string" && /^#?[\da-f]{6}$/i.test(accent.value.trim())));
      if (saved && saved.version === 1 && validAccent && ["light", "dark", "system"].includes(saved.theme)) preference = saved.theme;
    } catch { /* Keep the legacy theme if the versioned record is malformed. */ }
    if (preference !== "light" && preference !== "dark" && preference !== "system") {
      preference = "system";
    }
    var resolved = preference === "system"
      ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      : preference;
    window.document.documentElement.dataset.theme = resolved;
    window.document.documentElement.dataset.themePreference = preference;
    window.document.documentElement.style.colorScheme = resolved;
  } catch {
    window.document.documentElement.dataset.theme = "light";
    window.document.documentElement.dataset.themePreference = "system";
  }
}());
