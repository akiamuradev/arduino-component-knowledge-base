import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { Difficulty } from "../api/contracts";
import { useCurrentUser } from "../auth/queries";
import { useCatalog, catalogCategoriesQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { BrandSplat } from "../components/BrandSplat";
import { ComponentCard } from "../components/ComponentCard";
import { SplatEmptyState } from "../components/SplatEmptyState";

export function CatalogPage() {
  const currentUser = useCurrentUser();
  const [searchParams, setSearchParams] = useSearchParams();
  const query = searchParams.get("q") ?? "";
  const [categoryId, setCategoryId] = useState("");
  const [difficulty, setDifficulty] = useState<Difficulty | "">("");
  const categories = useQuery(catalogCategoriesQuery);
  const components = useCatalog({ query, categoryId, difficulty });
  const canEdit = currentUser.data?.roles.some((role) => role === "teacher" || role === "administrator") === true;

  return <section className="catalog-page">
    <div className="hero"><div className="hero__copy"><p className="eyebrow">Учебный каталог компонентов</p><h1>Исследуйте мир Arduino-компонентов</h1><p>Характеристики, совместимость, схемы подключения и проверенные источники в одном образовательном каталоге.</p><div className="hero__notes"><span>Только опубликованные материалы</span><span>Для Arduino-проектов</span></div>{canEdit ? <Link className="button button--accent" to="/admin/components/new">＋ Добавить компонент</Link> : null}</div><div className="hero__visual" aria-hidden="true"><BrandSplat animated className="hero__splat" loading="eager" rotation={-7} size="clamp(17rem, 31vw, 31rem)" variant="glow" /><div className="hero__board"><span className="hero__chip">UNO</span><i /><i /><i /><i /></div><span className="hero__line hero__line--one" /><span className="hero__line hero__line--two" /><span className="hero__node hero__node--one" /><span className="hero__node hero__node--two" /></div></div>
    <form className="catalog-filters" role="search" onSubmit={(event) => { event.preventDefault(); }}>
      <label>Поиск<input type="search" value={query} maxLength={100} placeholder="Например, датчик температуры" onChange={(event) => { const next = new URLSearchParams(searchParams); const value = event.target.value; if (value === "") next.delete("q"); else next.set("q", value); setSearchParams(next, { replace: true }); }} /></label>
      <label>Категория<select value={categoryId} disabled={categories.isPending} onChange={(event) => { setCategoryId(event.target.value); }}><option value="">Все категории</option>{categories.data?.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>Сложность<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value as Difficulty | ""); }}><option value="">Любая</option><option value="beginner">Начальная</option><option value="intermediate">Средняя</option><option value="advanced">Продвинутая</option></select></label>
    </form>
    {categories.isError ? <ErrorState message="Не удалось загрузить категории." onRetry={() => void categories.refetch()} /> : null}
    {components.isPending ? <LoadingState label="Ищем компоненты…" /> : components.isError ? <ErrorState message="Не удалось загрузить каталог." onRetry={() => void components.refetch()} /> : components.data.items.length === 0 ? <SplatEmptyState icon="⌕" title="Ничего не найдено" description="Измените поисковый запрос или фильтры." /> : <><div className="catalog-results"><p className="catalog-count" aria-live="polite">Найдено материалов: <strong>{components.data.total}</strong></p><span>Открывайте карточку, чтобы увидеть характеристики и примеры</span></div><div className="catalog-grid">{components.data.items.map((component) => <ComponentCard component={component} key={component.id} />)}</div></>}
  </section>;
}
