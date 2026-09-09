import { Link } from "react-router-dom";

import { PRODUCT_BRAND } from "../config/brand";
import { BuildInfo } from "./BuildInfo";

export function AppFooter() {
  return (
    <footer className="app-footer">
      <div className="app-footer__brand">
        <strong>{PRODUCT_BRAND.productName}</strong>
        <span>Автор: <a href={PRODUCT_BRAND.authorUrl} target="_blank" rel="noopener noreferrer">{PRODUCT_BRAND.authorName}</a></span>
      </div>
      <nav aria-label="Служебная навигация">
        <Link to="/about">О системе</Link>
        <Link to="/sources">Источники материалов</Link>
        <a href={PRODUCT_BRAND.licenseUrl} target="_blank" rel="noopener noreferrer">{PRODUCT_BRAND.licenseName}</a>
      </nav>
      <BuildInfo compact />
    </footer>
  );
}
