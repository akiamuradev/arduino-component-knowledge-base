export const canonicalLicense = __ACKB_LICENSE_TEXT__;

// Only presentation is parsed: no sentences, numbering or punctuation are rewritten.
export const licenseBlocks = canonicalLicense.trim().split(/\n\s*\n/).map((text) => {
  const title = text.trim();
  const numbered = /^(\d+)\. [^\n]+$/.exec(title);
  const id = numbered ? `gpl-section-${numbered[1] ?? ""}`
    : title === "Preamble" ? "gpl-preamble"
    : title === "How to Apply These Terms to Your New Programs" ? "gpl-how-to-apply" : undefined;
  const heading = id !== undefined || title === "TERMS AND CONDITIONS" || title === "END OF TERMS AND CONDITIONS"
    || title.startsWith("GNU GENERAL PUBLIC LICENSE\n");
  return { text, title, id, heading };
});
export const licenseContents = licenseBlocks.filter((block) => block.id !== undefined);
