"""Immutable commands and identifiers for import pipeline persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid5

from arduino_component_kb.imports.pipeline.models.composition import CompositionInput, ReviewDraft

PERSISTENCE_NAMESPACE = UUID("470113b9-2cb0-49ee-a099-7da40b9225ad")


class EnrichmentLifecycleStatus(StrEnum):
    SUGGESTED = "suggested"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    STALE = "stale"
    CONFLICT = "conflict"


class EnrichmentReviewDecision(StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class PipelinePersistenceInput:
    source_id: UUID
    composition: CompositionInput
    draft: ReviewDraft
    component_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.draft.input_sha256 != self.composition.input_sha256:
            raise ValueError("persistence_composition_input_mismatch")
        if self.draft.artifact != self.composition.facts.artifact:
            raise ValueError("persistence_artifact_mismatch")
        quality_sha256 = sha256(self.composition.quality_report.to_json().encode()).hexdigest()
        if self.draft.quality_report_sha256 != quality_sha256:
            raise ValueError("persistence_quality_report_mismatch")

    @property
    def artifact_id(self) -> UUID:
        artifact = self.draft.artifact
        key = ":".join(
            (
                str(self.source_id),
                artifact.source.source_revision or "unversioned",
                artifact.source.source_path or artifact.source.source_url or "missing",
                artifact.content_sha256,
            )
        )
        return uuid5(PERSISTENCE_NAMESPACE, f"artifact:{key}")

    @property
    def identity_id(self) -> UUID:
        digest = sha256(self.composition.identity.to_json().encode()).hexdigest()
        return uuid5(PERSISTENCE_NAMESPACE, f"identity:{self.artifact_id}:{digest}")

    @property
    def evaluation_id(self) -> UUID:
        report = self.composition.quality_report
        digest = sha256(report.to_json().encode()).hexdigest()
        return uuid5(PERSISTENCE_NAMESPACE, f"evaluation:{self.artifact_id}:{digest}")

    @property
    def review_draft_id(self) -> UUID:
        digest = sha256(self.draft.to_json().encode()).hexdigest()
        return uuid5(PERSISTENCE_NAMESPACE, f"draft:{self.artifact_id}:{digest}")

    def enrichment_id(
        self, external_identity: str, source_revision: str, relation_type: str
    ) -> UUID:
        return uuid5(
            PERSISTENCE_NAMESPACE,
            (
                f"enrichment:{self.review_draft_id}:kicad:{relation_type}:"
                f"{external_identity}:{source_revision}"
            ),
        )


@dataclass(frozen=True, slots=True)
class PersistedPipelineDraft:
    artifact_id: UUID
    identity_id: UUID
    evaluation_id: UUID
    review_draft_id: UUID
    enrichment_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class EnrichmentReviewCommand:
    enrichment_id: UUID
    reviewer_id: UUID
    decision: EnrichmentReviewDecision
    reason: str
    reviewed_at: datetime

    def __post_init__(self) -> None:
        if not self.reason.strip() or "\x00" in self.reason or len(self.reason) > 1_000:
            raise ValueError("enrichment_review_reason_invalid")
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("enrichment_reviewed_at_must_be_timezone_aware")
