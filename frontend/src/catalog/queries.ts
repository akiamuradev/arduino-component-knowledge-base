import { queryOptions, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { Difficulty } from "../api/contracts";

export interface CatalogFilters {
  query: string;
  categoryId: string;
  difficulty: Difficulty | "";
}

export const catalogKeys = {
  all: ["catalog"] as const,
  list: (filters: CatalogFilters) => ["catalog", "components", filters] as const,
  categories: ["catalog", "categories"] as const,
  sources: ["catalog", "sources"] as const,
  detail: (slug: string) => ["catalog", "component", slug] as const,
};

export const catalogCategoriesQuery = queryOptions({
  queryKey: catalogKeys.categories,
  queryFn: api.listCatalogCategories,
  staleTime: 300_000,
});

export const catalogSourcesQuery = queryOptions({
  queryKey: catalogKeys.sources,
  queryFn: api.listCatalogSources,
  staleTime: 300_000,
});

export function useCatalog(filters: CatalogFilters) {
  return useQuery({
    queryKey: catalogKeys.list(filters),
    queryFn: () => api.listCatalogComponents(filters),
  });
}

export const catalogComponentQuery = (slug: string) =>
  queryOptions({
    queryKey: catalogKeys.detail(slug),
    queryFn: () => api.getCatalogComponent(slug),
  });
