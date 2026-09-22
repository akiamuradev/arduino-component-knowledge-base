import { afterEach, describe, expect, it, vi } from "vitest";

import { focusValidationIssue } from "./validation-focus";

afterEach(() => {
  document.body.replaceChildren();
  vi.unstubAllGlobals();
});

describe("validation focus", () => {
  it.each([false, true])("focuses only the first mapped issue and respects reduced motion (%s)", (reduced) => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({ matches: reduced }));
    const slug = document.createElement("input");
    slug.id = "component-slug";
    const label = document.createElement("input");
    label.id = "specification-label-7";
    const slugScroll = vi.fn();
    slug.scrollIntoView = slugScroll;
    const labelScroll = vi.fn();
    label.scrollIntoView = labelScroll;
    document.body.append(slug, label);
    focusValidationIssue([
      { path: ["unmapped"], code: "unknown", meta: {} },
      { path: ["slug"], code: "slug_already_exists", meta: {} },
      { path: ["specifications", 7, "label"], code: "specification_definition_conflict", meta: {} },
    ]);
    expect(slug).toHaveFocus();
    expect(slugScroll).toHaveBeenCalledExactlyOnceWith({ block: "center", behavior: reduced ? "instant" : "smooth" });
    expect(labelScroll).not.toHaveBeenCalled();
    focusValidationIssue([{ path: ["specifications", 7, "label"], code: "specification_definition_conflict", meta: {} }]);
    expect(label).toHaveFocus();
  });
});
