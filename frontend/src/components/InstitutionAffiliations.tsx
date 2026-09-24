import { useId } from "react";

import { EDUCATIONAL_INSTITUTIONS } from "../config/institutions";
import "./institution-affiliations.css";

export function InstitutionAffiliations({ compact = false }: { compact?: boolean }) {
  const headingId = useId();
  return (
    <section className={`institutions${compact ? " institutions--compact" : ""}`} aria-labelledby={headingId}>
      <h2 id={headingId}>Связано с образовательными организациями{compact && <span className="sr-only"> — в подвале сайта</span>}</h2>
      <div className="institutions__cards">
        {EDUCATIONAL_INSTITUTIONS.map((institution) => (
          <a className="institution-card" key={institution.id} href={institution.url} target="_blank" rel="noopener noreferrer">
            <img src={institution.logo} alt={institution.alt} width={institution.width} height={institution.height} loading="lazy" decoding="async" />
            <span className="institution-card__copy">
              <strong>{compact ? institution.shortName : institution.name}</strong>
              {!compact && <span>{institution.url}</span>}
            </span>
            <span aria-hidden="true">↗</span>
          </a>
        ))}
      </div>
    </section>
  );
}
