import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import type { ImportRelationType } from "../api/contracts";

export const importReviewKeys = {
  all: ["import-reviews"] as const,
  detail: (reviewDraftId: string) => ["import-reviews", reviewDraftId] as const,
};

export function useImportReviews() {
  return useQuery({ queryKey: importReviewKeys.all, queryFn: api.listImportReviews });
}

export function useImportReview(reviewDraftId: string | undefined) {
  return useQuery({
    queryKey: importReviewKeys.detail(reviewDraftId ?? "none"),
    queryFn: () => api.getImportReview(reviewDraftId ?? ""),
    enabled: reviewDraftId !== undefined,
  });
}

function useReviewMutation<T>(
  reviewDraftId: string,
  mutationFn: (input: T) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: importReviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: importReviewKeys.detail(reviewDraftId) }),
      ]);
    },
  });
}

export function useEnrichmentDecision(reviewDraftId: string) {
  return useReviewMutation(
    reviewDraftId,
    (input: {
      enrichmentId: string;
      expectedRevision: number;
      decision: "accept" | "reject";
      reason: string;
    }) => api.decideImportEnrichment(reviewDraftId, input.enrichmentId, {
      expected_revision: input.expectedRevision,
      decision: input.decision,
      reason: input.reason,
    }),
  );
}

export function useEnrichmentRelation(reviewDraftId: string) {
  return useReviewMutation(
    reviewDraftId,
    (input: {
      enrichmentId: string;
      expectedRevision: number;
      relationType: ImportRelationType;
      reason: string;
    }) => api.changeImportEnrichmentRelation(reviewDraftId, input.enrichmentId, {
      expected_revision: input.expectedRevision,
      relation_type: input.relationType,
      reason: input.reason,
    }),
  );
}

export function useIdentitySelection(reviewDraftId: string) {
  return useReviewMutation(
    reviewDraftId,
    (input: { identityCandidateId: string; expectedRevision: number; reason: string }) =>
      api.selectImportIdentity(reviewDraftId, {
        expected_revision: input.expectedRevision,
        identity_candidate_id: input.identityCandidateId,
        reason: input.reason,
      }),
  );
}

export function useSpecificationMapping(reviewDraftId: string) {
  return useReviewMutation(
    reviewDraftId,
    (input: {
      specificationKey: string;
      taxonomyPath: string;
      expectedRevision: number;
      reason: string;
    }) => api.mapImportSpecification(reviewDraftId, {
      expected_revision: input.expectedRevision,
      specification_key: input.specificationKey,
      taxonomy_path: input.taxonomyPath,
      reason: input.reason,
    }),
  );
}

export function useParserIssue(reviewDraftId: string) {
  return useReviewMutation(
    reviewDraftId,
    (input: { code: string; note: string; expectedRevision: number }) =>
      api.markImportParserIssue(reviewDraftId, {
        expected_revision: input.expectedRevision,
        code: input.code,
        note: input.note,
      }),
  );
}

export function useDraftConfirmation(reviewDraftId: string) {
  return useReviewMutation(
    reviewDraftId,
    (input: { reason: string; expectedRevision: number }) =>
      api.confirmImportReview(reviewDraftId, {
        expected_revision: input.expectedRevision,
        reason: input.reason,
      }),
  );
}
