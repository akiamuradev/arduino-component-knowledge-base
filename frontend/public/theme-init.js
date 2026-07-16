(function () {
  try {
    var preference = window.localStorage.getItem("ackb-theme");
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
