import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { JobStatus } from "../api/contracts";

export const jobKeys = {
  all: ["admin", "jobs"] as const,
  list: (status?: JobStatus) => ["admin", "jobs", status ?? "all"] as const,
  imports: (status?: JobStatus) => ["admin", "jobs", "imports", status ?? "all"] as const,
};

export function useAdminJobs(status?: JobStatus) {
  return useQuery({
    queryKey: jobKeys.list(status),
    queryFn: () => api.listJobs(status),
    refetchInterval: 5_000,
  });
}

export function useAdminImportJobs(status?: JobStatus) {
  return useQuery({
    queryKey: jobKeys.imports(status),
    queryFn: () => api.listImportJobs(status),
    refetchInterval: 5_000,
  });
}

export function useRetryJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.retryJob,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}

export function useRetryImportJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.retryImportJob,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: jobKeys.all });
    },
  });
}
