import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { RepositoryImportInput } from "../api/contracts";

export const importKeys = {
  all: ["repository-imports"] as const,
  list: ["repository-imports", "list"] as const,
  job: (jobId: string) => ["repository-imports", "job", jobId] as const,
};

export function useImports() {
  return useQuery({
    queryKey: importKeys.list,
    queryFn: api.listImports,
    refetchInterval: 5_000,
  });
}

export function useRepositoryFileDiscovery() {
  return useMutation({ mutationFn: api.discoverRepositoryFiles });
}

export function useRepositoryEntryDiscovery() {
  return useMutation({ mutationFn: api.discoverRepositoryEntries });
}

export function useRepositoryPreview() {
  return useMutation({ mutationFn: api.previewRepositoryImport });
}

export function useCreateRepositoryImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ input, idempotencyKey }: { input: RepositoryImportInput; idempotencyKey: string }) =>
      api.createRepositoryImport(input, idempotencyKey),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: importKeys.list });
    },
  });
}

export function useRetryImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.retryImport,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: importKeys.list });
    },
  });
}

export function useCancelImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.cancelImport,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: importKeys.list });
    },
  });
}

export function useImportJob(jobId: string | null) {
  return useQuery({
    queryKey: importKeys.job(jobId ?? "none"),
    queryFn: () => api.getImportJob(jobId ?? ""),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" || status === "cancelled"
        ? false
        : 2_000;
    },
  });
}
