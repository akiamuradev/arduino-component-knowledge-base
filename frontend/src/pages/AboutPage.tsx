import { BuildInfo } from "../components/BuildInfo";
import { BrandSplat } from "../components/BrandSplat";
import { PRODUCT_BRAND } from "../config/brand";

export function AboutPage() {
  return (
    <article className="about-page">
      <header className="about-hero">
        <div className="about-hero__copy"><p className="eyebrow">О продукте</p><h1>{PRODUCT_BRAND.productName}</h1><p>Внутренняя образовательная платформа для ведения проверенного каталога Arduino-совместимых компонентов.</p></div>
        <BrandSplat className="about-hero__splat" loading="eager" rotation={-8} size="clamp(15rem, 29vw, 27rem)" variant="glow" />
      </header>
      <div className="about-grid">
        <section><p className="section-kicker">Назначение</p><h2>От знаний к практике</h2><p>Платформа помогает студентам находить характеристики и учебные примеры, а преподавателям — готовить и публиковать карточки в контролируемом редакционном процессе.</p></section>
        <section><p className="section-kicker">Автор платформы</p><h2>{PRODUCT_BRAND.authorName}</h2><p>Программный продукт разработан {PRODUCT_BRAND.authorName}. Организация-пользователь не заменяет автора платформы.</p><a className="text-link" href={PRODUCT_BRAND.officialRepository} target="_blank" rel="noopener noreferrer">Официальный репозиторий <span aria-hidden="true">↗</span></a></section>
        <section><p className="section-kicker">Лицензия приложения</p><h2>{PRODUCT_BRAND.licenseName}</h2><p>Лицензия приложения не определяет условия использования внешних материалов. Они указываются отдельно при наличии metadata.</p><a className="text-link" href={`${PRODUCT_BRAND.officialRepository}/blob/main/LICENCE`} target="_blank" rel="noopener noreferrer">Открыть текст лицензии <span aria-hidden="true">↗</span></a></section>
        <section><p className="section-kicker">Организация-пользователь</p><h2>Не настроена</h2><p>Backend пока не предоставляет отдельный контракт организационного branding. Авторство продукта остаётся неизменным.</p></section>
        <section><p className="section-kicker">Технологический стек</p><h2>React + FastAPI</h2><p>TypeScript frontend, PostgreSQL metadata, private MinIO media и Redis/Dramatiq workers объединены контролируемым backend API.</p></section>
      </div>
      <section className="about-sources" id="material-sources">
        <p className="section-kicker">Прозрачность</p>
        <h2>Источники материалов</h2>
        <p>Импортированный материал должен показывать точную исходную страницу и дату импорта. Если backend не передал provenance, интерфейс не создаёт источник самостоятельно.</p>
        <p>Пилотные сайты, разрешённые конфигурацией импорта: <code>arduino-tex.ru</code>, <code>portal-pk.ru</code> и <code>alexgyver.ru</code>. Наличие сайта в allowlist не означает разрешение на копирование и не заменяет проверку лицензии материала.</p>
      </section>
      <section className="about-build"><p className="section-kicker">Сборка</p><h2>Build information</h2><BuildInfo /></section>
    </article>
  );
}
