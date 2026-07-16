import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { catalogComponentQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";

const targetLabels = { board: "Плата", library: "Библиотека", platform: "Платформа" };

export function CatalogComponentPage() {
  const { slug = "" } = useParams();
  const component = useQuery({ ...catalogComponentQuery(slug), enabled: slug !== "" });
  if (component.isPending) return <LoadingState label="Загружаем карточку…" />;
  if (component.isError) {
    return <ErrorState message="Карточка не найдена или больше не опубликована." onRetry={() => void component.refetch()} />;
  }
  const card = component.data;
  return <article className="student-card">
    <Link to="/">← К каталогу</Link>
    <header><p className="eyebrow">{card.primary_category.name}</p><h1>{card.title}</h1><p className="preview-summary">{card.summary}</p><div className="tag-list">{card.aliases.map((alias) => <span key={alias}>{alias}</span>)}</div></header>
    <section><h2>Описание</h2><p className="preserve-lines">{card.description}</p></section>
    {card.purpose ? <section><h2>Назначение</h2><p>{card.purpose}</p></section> : null}
    {card.specifications.length > 0 ? <section><h2>Характеристики</h2><dl className="specification-list">{card.specifications.map((item) => <div key={item.key}><dt>{item.label}</dt><dd>{item.value_text}{item.unit ? ` ${item.unit}` : ""}</dd></div>)}</dl></section> : null}
    {card.compatibility.length > 0 ? <section><h2>Совместимость</h2><ul className="compatibility-list">{card.compatibility.map((item) => <li key={`${item.target_type}:${item.name}:${item.version_constraint ?? ""}`}><strong>{targetLabels[item.target_type]}: {item.name}</strong>{item.version_constraint ? <span>{item.version_constraint}</span> : null}{item.notes ? <p>{item.notes}</p> : null}</li>)}</ul></section> : null}
    {card.usage_notes ? <section><h2>Использование</h2><p className="preserve-lines">{card.usage_notes}</p></section> : null}
    {card.safety_notes ? <section className="safety-callout"><h2>Безопасность</h2><p className="preserve-lines">{card.safety_notes}</p></section> : null}
    <footer><span>{card.manufacturer ?? "Производитель не указан"}</span><span>{card.model ?? "Модель не указана"}</span><span>{card.difficulty}</span></footer>
  </article>;
}
