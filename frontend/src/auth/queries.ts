import { queryOptions, useQuery } from "@tanstack/react-query";

import { api, ApiError } from "../api/client";

export const currentUserQueryKey = ["auth", "current-user"] as const;

export const currentUserQuery = queryOptions({
  queryKey: currentUserQueryKey,
  queryFn: api.currentUser,
  retry: (failureCount, error) =>
    error instanceof ApiError && (error.status === 401 || error.status === 403)
      ? false
      : failureCount < 1,
  staleTime: 30_000,
});

export function useCurrentUser() {
  return useQuery(currentUserQuery);
}
