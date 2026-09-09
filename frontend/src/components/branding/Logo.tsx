/** Original modular ACKB lettering; no font or embedded bitmap is used. */
export function LogoGlyphs() {
  return <g fill="currentColor" fillRule="evenodd"><path d="M4 24V4H32V10H10V24ZM156 24V4H128V10H150V24ZM4 64V84H32V78H10V64ZM156 64V84H128V78H150V64Z" /><path d="M17 61L29 27H37L49 61H41L38 52H27L24 61ZM29 45H36L32.5 34ZM55 27H77V34H59L55 38V50L59 54H77V61H55L47 53V35ZM82 27H90V41L103 27H113L97 44L114 61H103L90 48V61H82ZM118 27H140L148 35V42L144 45L148 49V54L141 61H118ZM126 34V41H138L140 39V36L138 34ZM126 48V54H138L140 52V50L138 48Z" /></g>;
}

export function LogoCompact({ className = "" }: { className?: string }) {
  return <svg className={`ackb-logo ${className}`} viewBox="0 0 160 88" aria-hidden="true" focusable="false"><LogoGlyphs /></svg>;
}

export function LogoPrimary({ monochrome = false }: { monochrome?: boolean }) {
  return <LogoCompact className={monochrome ? "ackb-logo--primary ackb-logo--mono" : "ackb-logo--primary"} />;
}

export function LogoHeader() {
  return <><LogoCompact /><span className="brand__copy"><strong>База компонентов Arduino</strong><small>Справочник электронных компонентов</small></span></>;
}
