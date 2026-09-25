import { Link } from "react-router-dom";
import { useId } from "react";

import { PRODUCT_BRAND } from "../config/brand";
import { BuildInfo } from "./BuildInfo";
import { InstitutionAffiliations } from "./InstitutionAffiliations";

export function AppFooter() {
  const headingId = useId();
  return (
    <footer className="app-footer">
      <div className="app-footer__brand">
        <strong>{PRODUCT_BRAND.productName}</strong>
        <span>Автор: <a href={PRODUCT_BRAND.authorUrl} target="_blank" rel="noopener noreferrer">{PRODUCT_BRAND.authorName}</a></span>
        <h2 id={headingId}>Связано с образовательными организациями<span className="sr-only"> — в подвале сайта</span></h2>
      </div>
      <InstitutionAffiliations compact labelledBy={headingId} />
      <div className="app-footer__services">
        <nav aria-label="Служебная навигация">
          <Link to="/about">О системе</Link>
          <Link to="/sources">Источники материалов</Link>
          <Link to={PRODUCT_BRAND.licenseUrl}>{PRODUCT_BRAND.licenseName}</Link>
        </nav>
        <BuildInfo compact />
      </div>
    </footer>
  );
}
