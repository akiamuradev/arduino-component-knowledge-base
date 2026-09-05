import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import type { Difficulty } from "../api/contracts";
import { hasPermission } from "../auth/permissions";
import { useCurrentUser } from "../auth/queries";
import { useCatalog, catalogCategoriesQuery } from "../catalog/queries";
import { ErrorState, LoadingState } from "../components/AsyncStates";
import { HardwareBoard } from "../components/HardwareBoard";
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
  const activeFilters = [
    categoryId === "" ? null : categories.data?.find((category) => category.id === categoryId)?.name,
    difficulty === "" ? null : { beginner: "Начальная", intermediate: "Средняя", advanced: "Продвинутая" }[difficulty],
  ].filter(Boolean);
  const canCreate = currentUser.data === undefined
    ? false
    : hasPermission(currentUser.data, "components.create");

  const resetFilters = () => {
    setCategoryId("");
    setDifficulty("");
    const next = new URLSearchParams(searchParams);
    next.delete("q");
    setSearchParams(next, { replace: true });
  };

  return <section className="catalog-page catalog-workbench">
    <aside className="catalog-sidebar" aria-label="Фильтры компонентов">
      <h2>Фильтры</h2>
      <label>Категория<select value={categoryId} disabled={categories.isPending} onChange={(event) => { setCategoryId(event.target.value); }}><option value="">Все категории</option>{categories.data?.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label>
      <label>Сложность<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value as Difficulty | ""); }}><option value="">Любая</option><option value="beginner">Начальная</option><option value="intermediate">Средняя</option><option value="advanced">Продвинутая</option></select></label>
      <button className="button button--quiet" type="button" disabled={query === "" && categoryId === "" && difficulty === ""} onClick={resetFilters}>Сбросить фильтры</button>
      {categories.isError ? <ErrorState message="Не удалось загрузить категории." onRetry={() => void categories.refetch()} /> : null}
    </aside>
    <div className="catalog-workspace">
      <header className="catalog-intro">
        <div><h1>Каталог компонентов</h1><p>Характеристики, интерфейсы, совместимость, схемы и источники.</p>
          {canCreate ? <Link className="button button--accent" to="/admin/components/new">＋ Добавить компонент</Link> : null}
        </div>
        <HardwareBoard />
      </header>
    <form aria-label="Поиск по каталогу" className="catalog-toolbar" role="search" onSubmit={(event) => { event.preventDefault(); }}>
      <label>Поиск<input type="search" value={query} maxLength={100} placeholder="Например, датчик температуры" onChange={(event) => { const next = new URLSearchParams(searchParams); const value = event.target.value; if (value === "") next.delete("q"); else next.set("q", value); setSearchParams(next, { replace: true }); }} /></label>
      <p className="catalog-count" role="status">{components.isSuccess ? <>Найдено: <strong>{components.data.total}</strong></> : components.isPending ? "Загрузка…" : "Каталог недоступен"}</p>
      {activeFilters.length > 0 ? <p className="catalog-active-filters" aria-label="Активные фильтры">{activeFilters.join(" · ")}</p> : null}
    </form>
    {components.isPending ? <LoadingState label="Ищем компоненты…" /> : components.isError ? <ErrorState message="Не удалось загрузить каталог." onRetry={() => void components.refetch()} /> : components.data.items.length === 0 ? <SplatEmptyState icon="⌕" title="Ничего не найдено" description="Измените поисковый запрос или фильтры." /> : <div className="catalog-grid">{components.data.items.map((component) => <ComponentCard component={component} key={component.id} />)}</div>}
    </div>
  </section>;
}
