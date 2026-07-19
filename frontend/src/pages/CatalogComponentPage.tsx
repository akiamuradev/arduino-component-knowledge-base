import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { catalogComponentQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { LearningExample } from "../components/LearningExample";
import { MediaGallery } from "../components/MediaGallery";
import { SourceAttributionBlock } from "../components/SourceAttributionBlock";

const targetLabels = { board: "Плата", library: "Библиотека", platform: "Платформа" };
const difficultyLabels = {
  beginner: "Начальный уровень",
  intermediate: "Средний уровень",
  advanced: "Продвинутый уровень",
};

export function CatalogComponentPage() {
  const { slug = "" } = useParams();
  const component = useQuery({ ...catalogComponentQuery(slug), enabled: slug !== "" });
  if (component.isPending) return <LoadingState label="Загружаем карточку…" />;
  if (component.isError) {
    return <ErrorState message="Карточка не найдена или больше не опубликована." onRetry={() => void component.refetch()} />;
  }
  const card = component.data;
  return <article className="student-card">
    <Link className="breadcrumb" to="/"><span aria-hidden="true">←</span> Каталог компонентов</Link>
    <header className="student-card__hero"><div><div className="student-card__meta"><span className="status-badge status-badge--published">{card.primary_category.name}</span><span>{difficultyLabels[card.difficulty]}</span>{card.model ? <span>{card.model}</span> : null}</div><h1>{card.title}</h1><p className="preview-summary">{card.summary}</p><div className="tag-list">{[...new Set([...card.aliases, ...card.tags])].map((tag) => <span key={tag}>{tag}</span>)}</div></div><div className="student-card__visual">{card.media !== undefined && card.media.length > 0 ? <MediaGallery items={card.media} /> : <div className="component-symbol" role="img" aria-label={`Изображение для ${card.title} пока не добавлено`}><span aria-hidden="true">{card.title.charAt(0).toUpperCase()}</span><i /><i /><i /><i /></div>}</div></header>
    <div className="student-card__content">
      <div className="student-card__main">
        <section><p className="section-kicker">01 / О компоненте</p><h2>Описание</h2><p className="preserve-lines">{card.description}</p></section>
        {card.purpose ? <section><p className="section-kicker">02 / Задача</p><h2>Назначение</h2><p>{card.purpose}</p></section> : null}
        {card.specifications.length > 0 ? <section><p className="section-kicker">03 / Параметры</p><h2>Характеристики</h2><dl className="specification-list">{card.specifications.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value_text}{item.unit ? ` ${item.unit}` : ""}</dd></div>)}</dl></section> : null}
        {card.compatibility.length > 0 ? <section><p className="section-kicker">04 / Подключение</p><h2>Совместимость</h2><ul className="compatibility-list">{card.compatibility.map((item) => <li key={`${item.target_type}:${item.name}:${item.version_constraint ?? ""}`}><strong>{targetLabels[item.target_type]}: {item.name}</strong>{item.version_constraint ? <span>{item.version_constraint}</span> : null}{item.notes ? <p>{item.notes}</p> : null}</li>)}</ul></section> : null}
        {card.usage_notes ? <section><h2>Использование</h2><p className="preserve-lines">{card.usage_notes}</p></section> : null}
        {card.safety_notes ? <section className="safety-callout"><p className="section-kicker">Важно</p><h2>Безопасность</h2><p className="preserve-lines">{card.safety_notes}</p></section> : null}
        {card.code_examples.length > 0 ? <section><p className="section-kicker">Практикум</p><h2>Попробуйте сами</h2>{card.code_examples.map((example) => <LearningExample example={example} key={`${String(example.position)}:${example.title}`} />)}</section> : null}
        <SourceAttributionBlock sources={card.sources} />
      </div>
      <aside className="component-facts" aria-label="Краткие сведения"><p className="eyebrow">Кратко</p><dl><div><dt>Производитель</dt><dd>{card.manufacturer ?? "Не указан"}</dd></div><div><dt>Модель</dt><dd>{card.model ?? "Не указана"}</dd></div><div><dt>Уровень</dt><dd>{difficultyLabels[card.difficulty]}</dd></div><div><dt>Категория</dt><dd>{card.primary_category.name}</dd></div></dl></aside>
    </div>
    <footer className="student-card__footer"><span>Опубликовано: {new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "long", year: "numeric" }).format(new Date(card.published_at))}</span><Link to="/">Смотреть другие компоненты →</Link></footer>
  </article>;
}
