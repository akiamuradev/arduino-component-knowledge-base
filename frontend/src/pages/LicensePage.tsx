import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AppFooter } from "../components/AppFooter";
import { SiteSettingsButton } from "../components/SiteSettingsButton";
import { LogoCompact } from "../components/branding/Logo";
import { PRODUCT_BRAND } from "../config/brand";
import { canonicalLicense, licenseBlocks, licenseContents } from "../legal/license";
import "./license-page.css";

const explanations = [
  ["Свободное ПО", "Можно использовать, изучать, изменять и распространять."],
  ["Copyleft", "При распространении производных работ применяются условия GNU GPL."],
  ["Исходный код", "Условия GPL обеспечивают получателям доступ к соответствующему исходному коду в предусмотренных лицензией случаях."],
  ["Без гарантии", "Программа предоставляется без каких-либо гарантий в пределах, разрешённых законом."],
] as const;

export function LicensePage() {
  const toc = useRef<HTMLDetailsElement>(null);
  const [wide, setWide] = useState(() => window.matchMedia("(min-width: 901px)").matches);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 901px)");
    const update = () => { setWide(media.matches); };
    media.addEventListener("change", update);
    return () => { media.removeEventListener("change", update); };
  }, []);
  const { hash } = useLocation();
  useEffect(() => {
    // Also honor direct /license#... URLs after the SPA has mounted.
    const target = document.getElementById(hash.slice(1));
    if (hash && target) { target.scrollIntoView(); target.focus({ preventScroll: true }); }
  }, [hash]);
  return <div className="app-shell license-shell">
    <a className="catalog-skip-link" href="#license-main">К содержанию лицензии</a>
    <header className="license-header">
      <Link className="license-header__brand" to="/" aria-label="ACKB — на главную"><LogoCompact /><span>{PRODUCT_BRAND.shortName}</span></Link>
      <nav aria-label="Навигация страницы лицензии"><Link className="text-link" to="/login">Войти</Link><SiteSettingsButton /></nav>
    </header>
    <main id="license-main" className="license-page" tabIndex={-1}>
      <header className="license-hero">
        <p className="eyebrow">Лицензия</p>
        <h1>GNU General Public License</h1>
        <span className="license-badge">{PRODUCT_BRAND.licenseSpdx}</span>
        <p className="license-lede">ACKB — свободное программное обеспечение. Код можно использовать, изучать, изменять и распространять на условиях GNU GPL версии 3 или любой более поздней версии.</p>
        <div className="license-identity"><strong>{canonicalLicense.split("\n")[0]}</strong><span>Copyright {PRODUCT_BRAND.copyright}</span><code>SPDX-License-Identifier: {PRODUCT_BRAND.licenseSpdx}</code></div>
        <div className="license-actions"><a className="button button--accent" href={PRODUCT_BRAND.officialRepository} target="_blank" rel="noopener noreferrer">Исходный код</a><a className="button button--quiet" href="#gpl-text">Полный текст GPL</a></div>
      </header>
      <section className="license-overview" aria-labelledby="license-overview-title">
        <h2 id="license-overview-title">Кратко о лицензии</h2>
        <p>Это только пояснение. Юридические условия определяет полный канонический текст лицензии ниже.</p>
        <div className="license-cards">{explanations.map(([title, description]) => <section key={title}><h3>{title}</h3><p>{description}</p></section>)}</div>
      </section>
      <section className="license-third-party" aria-labelledby="license-third-party-title">
        <h2 id="license-third-party-title">Сторонние материалы</h2>
        <p>Сторонние материалы сохраняют собственные лицензии и сведения об авторстве. Условия лицензии программного кода ACKB не заменяют условия этих материалов.</p>
        <div className="license-reference-links">{["THIRD_PARTY_NOTICES.md", "docs/DATA_LICENSING.md"].map((path) => <a className="text-link" key={path} href={`${PRODUCT_BRAND.officialRepository}/blob/main/${path}`} target="_blank" rel="noopener noreferrer">{path}</a>)}</div>
      </section>
      <div className="license-reading-layout">
        <aside className="license-toc">
          <h2 className="license-toc__title">Оглавление</h2>
          <details ref={toc} open={wide}>
            <summary>Оглавление</summary>
            <nav aria-label="Оглавление лицензии" lang="en">
              {licenseContents.map((block) => <a key={block.id} href={`#${block.id ?? ""}`} onClick={() => {
                if (!wide && toc.current) toc.current.open = false;
                // Native fragment navigation scrolls; explicit focus supports keyboard reading.
                document.getElementById(block.id ?? "")?.focus({ preventScroll: true });
              }}>{block.title}</a>)}
            </nav>
          </details>
        </aside>
        <section id="gpl-text" className="license-document" aria-labelledby="gpl-text-title" tabIndex={-1}>
          <h2 id="gpl-text-title">Полный текст лицензии</h2>
          <p className="license-document__source"><a className="text-link" href="/LICENCE.txt" download="LICENCE.txt">Скачать исходный текст LICENCE</a></p>
          <div className="license-document__body" lang="en">{licenseBlocks.map((block, index) => <Fragment key={index}>
            {block.heading ? <h3 id={block.id} tabIndex={block.id ? -1 : undefined}>{block.text}</h3> : <p>{block.text}</p>}{"\n\n"}
          </Fragment>)}</div>
        </section>
      </div>
    </main>
    <AppFooter />
  </div>;
}
