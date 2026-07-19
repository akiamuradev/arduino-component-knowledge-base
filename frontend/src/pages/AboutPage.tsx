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
        <section><p className="section-kicker">Лицензия приложения</p><h2>{PRODUCT_BRAND.licenseName}</h2><p>PolyForm Noncommercial относится к коду ACKB. Импортированные материалы сохраняют лицензии Seeed Studio Wiki или Official KiCad Libraries и собственную attribution.</p><a className="text-link" href={`${PRODUCT_BRAND.officialRepository}/blob/main/LICENCE`} target="_blank" rel="noopener noreferrer">Открыть текст лицензии <span aria-hidden="true">↗</span></a></section>
        <section><p className="section-kicker">Организация-пользователь</p><h2>Не настроена</h2><p>Backend пока не предоставляет отдельный контракт организационного branding. Авторство продукта остаётся неизменным.</p></section>
        <section><p className="section-kicker">Технологический стек</p><h2>React + FastAPI</h2><p>TypeScript frontend, PostgreSQL metadata, private MinIO media и Redis/Dramatiq workers объединены контролируемым backend API.</p></section>
      </div>
      <section className="about-sources" id="material-sources">
        <p className="section-kicker">Прозрачность</p>
        <h2>Источники материалов</h2>
        <p>Импортированный материал показывает исходный repository, зафиксированный commit, файл, parser version, лицензию и сведения о преобразованиях. Если backend не передал source snapshot, интерфейс не создаёт его самостоятельно.</p>
        <p>Действующие источники: Seeed Studio Wiki и Official KiCad Libraries. Arduino-Tex, Portal-PK и AlexGyver не используются для импорта; владелец AlexGyver отдельно запретил использование материалов.</p>
        <p>Проект не аффилирован с Arduino, Seeed Studio или KiCad. Названия и товарные знаки принадлежат соответствующим правообладателям.</p>
        <Link className="text-link" to="/sources">Открыть реестр источников →</Link>
      </section>
      <section className="about-build"><p className="section-kicker">Сборка</p><h2>Build information</h2><BuildInfo /></section>
    </article>
  );
}
import { Link } from "react-router-dom";
