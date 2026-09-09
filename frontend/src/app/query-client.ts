import { QueryCache, QueryClient } from "@tanstack/react-query";

import { ApiError } from "../api/client";
import { clearPrivateQueries, currentUserQueryKey, isCurrentUserQuery } from "../auth/session-cache";

export function createQueryClient(): QueryClient {
  const client = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (!(error instanceof ApiError) || error.status !== 401) return;
        // Keep the auth error so route guards can redirect; discard private data.
        void clearPrivateQueries(client);
        if (!isCurrentUserQuery(query.queryKey)) {
          void client.resetQueries({ queryKey: currentUserQueryKey, exact: true });
        }
      },
    }),
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
  return client;
}
