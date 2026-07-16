import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import type { Difficulty } from "../api/contracts";
import { useCatalog, catalogCategoriesQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";

export function CatalogPage() {
  const [query, setQuery] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty | "">("");
  const categories = useQuery(catalogCategoriesQuery);
  const components = useCatalog({ query, categoryId, difficulty });

  return <section>
    <div className="hero"><div><p className="eyebrow">Учебный каталог</p><h1>Компоненты Arduino — понятно и по делу</h1><p>Ищите опубликованные преподавателем карточки по названию, назначению и категории.</p></div><div className="hero__circuit" aria-hidden="true"><span /><span /><span /></div></div>
    <form className="catalog-filters" role="search" onSubmit={(event) => { event.preventDefault(); }}>
      <label>Поиск<input type="search" value={query} maxLength={100} placeholder="Например, датчик температуры" onChange={(event) => { setQuery(event.target.value); }} /></label>
      <label>Категория<select value={categoryId} disabled={categories.isPending} onChange={(event) => { setCategoryId(event.target.value); }}><option value="">Все категории</option>{categories.data?.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>Сложность<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value as Difficulty | ""); }}><option value="">Любая</option><option value="beginner">Начальная</option><option value="intermediate">Средняя</option><option value="advanced">Продвинутая</option></select></label>
    </form>
    {categories.isError ? <ErrorState message="Не удалось загрузить категории." onRetry={() => void categories.refetch()} /> : null}
    {components.isPending ? <LoadingState label="Ищем компоненты…" /> : components.isError ? <ErrorState message="Не удалось загрузить каталог." onRetry={() => void components.refetch()} /> : components.data.items.length === 0 ? <div className="empty-panel"><h2>Ничего не найдено</h2><p>Измените поисковый запрос или фильтры.</p></div> : <><p className="catalog-count" aria-live="polite">Найдено: {components.data.total}</p><div className="catalog-grid">{components.data.items.map((component) => <Link className="catalog-card" key={component.id} to={`/components/${component.slug}`}><span className="status-badge status-badge--published">{component.primary_category.name}</span><h2>{component.title}</h2><p>{component.summary}</p><div className="tag-list">{component.tags.slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div><small>{component.difficulty}</small></Link>)}</div></>}
  </section>;
}
