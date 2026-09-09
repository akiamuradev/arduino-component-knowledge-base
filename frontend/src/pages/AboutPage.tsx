import { BuildInfo } from "../components/BuildInfo";
import { LogoPrimary } from "../components/branding/Logo";
import { PRODUCT_BRAND } from "../config/brand";

export function AboutPage() {
  return (
    <article className="about-page">
      <header className="about-hero">
        <div className="about-hero__copy"><p className="eyebrow">О продукте</p><h1>{PRODUCT_BRAND.productName}</h1><p>База электронных компонентов с характеристиками, схемами и источниками.</p></div>
        <LogoPrimary />
      </header>
      <div className="about-grid">
        <section><p className="section-kicker">Назначение</p><h2>Каталог и редакция</h2><p>Поиск компонентов, техническая документация, подготовка и проверка материалов перед публикацией.</p></section>
        <section><p className="section-kicker">Автор платформы</p><h2>{PRODUCT_BRAND.authorName}</h2><p>Программный продукт разработан {PRODUCT_BRAND.authorName}.</p><a className="text-link" href={PRODUCT_BRAND.officialRepository} target="_blank" rel="noopener noreferrer">Официальный репозиторий <span aria-hidden="true">↗</span></a></section>
        <section><p className="section-kicker">Лицензия приложения</p><h2>{PRODUCT_BRAND.licenseName}</h2><p>Код ACKB распространяется по GNU GPL версии 3.0 или любой более поздней версии (GPL-3.0-or-later). Автор: akiamuradev. Импортированные материалы сохраняют лицензии Seeed Studio Wiki или официальных библиотек KiCad и собственные сведения об авторстве.</p><a className="text-link" href={PRODUCT_BRAND.licenseUrl} target="_blank" rel="noopener noreferrer">Открыть текст лицензии <span aria-hidden="true">↗</span></a></section>

        <section><p className="section-kicker">Архитектура</p><h2>Разграничение доступа</h2><p>Доступ к каталогу, редактированию материалов и управлению системой определяется правами учётной записи.</p></section>
      </div>
      <section className="about-sources" id="material-sources">
        <p className="section-kicker">Прозрачность</p>
        <h2>Источники материалов</h2>
        <p>Импортированный материал показывает исходный репозиторий, зафиксированный коммит, файл, версию импорта, лицензию и сведения о преобразованиях. Если подтверждённый снимок источника отсутствует, интерфейс не создаёт его самостоятельно.</p>
        <p>Материалы могут ссылаться на Seeed Studio Wiki и официальные библиотеки KiCad. Текущий статус каждого источника указан в реестре. Arduino-Tex, Portal-PK и AlexGyver не используются для импорта; владелец AlexGyver отдельно запретил использование материалов.</p>
        <p>Проект не аффилирован с Arduino, Seeed Studio или KiCad. Названия и товарные знаки принадлежат соответствующим правообладателям.</p>
        <Link className="text-link" to="/sources">Открыть реестр источников →</Link>
      </section>
      <section className="about-build"><p className="section-kicker">Сборка</p><h2>Информация о сборке</h2><BuildInfo /></section>
    </article>
  );
}
import { Link } from "react-router-dom";
