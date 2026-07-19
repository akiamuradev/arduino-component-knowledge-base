import { useMutation, useQuery } from "@tanstack/react-query";

import { api } from "../api/client";
import type { RepositoryImportInput } from "../api/contracts";

export const importKeys = {
  all: ["repository-imports"] as const,
  job: (jobId: string) => ["repository-imports", "job", jobId] as const,
};

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
  return useMutation({
    mutationFn: ({ input, idempotencyKey }: { input: RepositoryImportInput; idempotencyKey: string }) =>
      api.createRepositoryImport(input, idempotencyKey),
  });
}

export function useImportJob(jobId: string | null) {
  return useQuery({
    queryKey: importKeys.job(jobId ?? "none"),
    queryFn: () => api.getImportJob(jobId ?? ""),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 2_000;
    },
  });
}
