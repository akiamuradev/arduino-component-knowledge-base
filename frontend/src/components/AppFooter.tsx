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
        <Link to={PRODUCT_BRAND.licenseUrl}>{PRODUCT_BRAND.licenseName}</Link>
      </nav>
      <BuildInfo compact />
    </footer>
  );
}
