import { Link } from "react-router-dom";

import { PRODUCT_BRAND } from "../config/brand";
import { BuildInfo } from "./BuildInfo";

export function AppFooter() {
  return (
    <footer className="app-footer">
      <div className="app-footer__brand">
        <strong>{PRODUCT_BRAND.productName}</strong>
        <span>by <a href={PRODUCT_BRAND.authorUrl} target="_blank" rel="noopener noreferrer">{PRODUCT_BRAND.authorName}</a></span>
      </div>
      <nav aria-label="Служебная навигация">
        <Link to="/about">О системе</Link>
        <Link to="/sources">Источники материалов</Link>
        <a href={`${PRODUCT_BRAND.officialRepository}/blob/main/LICENCE`} target="_blank" rel="noopener noreferrer">Лицензия</a>
      </nav>
      <BuildInfo compact />
    </footer>
  );
}
