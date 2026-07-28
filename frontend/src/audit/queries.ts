import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { AuditEventFilters } from "../api/contracts";

export const auditKeys = {
  all: ["administration", "audit"] as const,
  list: (filters: AuditEventFilters) => ["administration", "audit", filters] as const,
};

export function useAuditEvents(filters: AuditEventFilters) {
  return useQuery({
    queryKey: auditKeys.list(filters),
    queryFn: () => api.listAuditEvents(filters),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}
