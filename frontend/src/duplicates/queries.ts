import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { DuplicateDecisionInput } from "../api/contracts";

export const duplicateKeys = {
  all: ["admin", "duplicates"] as const,
  detail: (id: string) => ["admin", "duplicates", id] as const,
};

export function useDuplicateCandidates() {
  return useQuery({ queryKey: duplicateKeys.all, queryFn: api.listDuplicateCandidates });
}

export function useDuplicateCandidate(id: string | undefined) {
  return useQuery({
    queryKey: duplicateKeys.detail(id ?? "none"),
    queryFn: () => api.getDuplicateCandidate(id ?? ""),
    enabled: id !== undefined,
  });
}

export function useDuplicateDecision(candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: DuplicateDecisionInput) => api.decideDuplicate(candidateId, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: duplicateKeys.all });
    },
  });
}
