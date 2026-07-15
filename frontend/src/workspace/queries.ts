import { queryOptions, useQuery } from "@tanstack/react-query";

import type { ComponentStatus } from "../api/contracts";
import { api } from "../api/client";

export const workspaceKeys = {
  all: ["workspace"] as const,
  componentLists: ["workspace", "components"] as const,
  components: (status?: ComponentStatus) => ["workspace", "components", status ?? "all"] as const,
  component: (componentId: string) => ["workspace", "component", componentId] as const,
  categories: ["workspace", "categories"] as const,
};

export const workspaceComponentsQuery = (status?: ComponentStatus) =>
  queryOptions({
    queryKey: workspaceKeys.components(status),
    queryFn: () => api.listWorkspaceComponents(status),
  });

export const workspaceComponentQuery = (componentId: string) =>
  queryOptions({
    queryKey: workspaceKeys.component(componentId),
    queryFn: () => api.getWorkspaceComponent(componentId),
  });

export const workspaceCategoriesQuery = queryOptions({
  queryKey: workspaceKeys.categories,
  queryFn: api.listWorkspaceCategories,
  staleTime: 5 * 60_000,
});

export function useWorkspaceComponents(status?: ComponentStatus) {
  return useQuery(workspaceComponentsQuery(status));
}
