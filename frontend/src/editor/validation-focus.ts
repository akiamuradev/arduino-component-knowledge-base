import type { ValidationIssue } from "../api/errors";

function focusElement(element: HTMLElement): void {
  element.scrollIntoView({ block: "center", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  element.focus({ preventScroll: true });
}

export function focusValidationIssue(issues: ValidationIssue[]): void {
  for (const { path } of issues) {
    let id: string | undefined;
    if (path.length === 1 && path[0] === "slug") id = "component-slug";
    if (path.length === 3 && path[0] === "specifications" && typeof path[1] === "number"
      && Number.isInteger(path[1]) && path[1] >= 0 && path[1] < 50) {
      if (path[2] === "label") id = `specification-label-${String(path[1])}`;
      if (path[2] === "value_text") id = `specification-value-${String(path[1])}`;
    }
    const element = id ? document.getElementById(id) : null;
    if (!element) continue;
    focusElement(element);
    return;
  }
  const clientInvalid = document.querySelector<HTMLElement>(".editor-form [aria-invalid='true']");
  if (clientInvalid) focusElement(clientInvalid);
}
