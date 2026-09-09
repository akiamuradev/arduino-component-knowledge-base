import { LogoCompact } from "./branding/Logo";

export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <LogoCompact />
    </span>
  );
}
