import type { QueryClient } from "@tanstack/react-query";

import type { User } from "../api/contracts";
import { clearEditorRecovery } from "../editor/recovery";

export const currentUserQueryKey = ["auth", "current-user"] as const;

export function isCurrentUserQuery(key: readonly unknown[]): boolean {
  return key.length === 2 && key[0] === "auth" && key[1] === "current-user";
}

// Cancellation detaches late query responses before the next identity owns the cache.
export async function replaceSessionCache(client: QueryClient, user?: User): Promise<void> {
  clearEditorRecovery();
  await client.cancelQueries();
  client.clear();
  if (user !== undefined) client.setQueryData(currentUserQueryKey, user);
}

export async function clearPrivateQueries(client: QueryClient): Promise<void> {
  const filters = { predicate: (query: { queryKey: readonly unknown[] }) => !isCurrentUserQuery(query.queryKey) };
  await client.cancelQueries(filters);
  client.removeQueries(filters);
  client.getMutationCache().clear();
}
