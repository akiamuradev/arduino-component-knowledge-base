import { BrandSplat } from "./BrandSplat";

export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <BrandSplat loading="eager" rotation={-6} size="100%" />
      <span className="brand-mark__core">A</span>
    </span>
  );
}
