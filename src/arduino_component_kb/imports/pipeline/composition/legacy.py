"""Explicit adapter from the new review draft to the current repository draft contract."""

from __future__ import annotations

from dataclasses import dataclass

from arduino_component_kb.imports.pipeline.models import (
    DraftConfidence,
    EvidenceFragment,
    ReviewDraft,
)
from arduino_component_kb.imports.repository_domain import (
    Confidence,
    FieldProvenance,
    LicenseSnapshot,
    ParsedRepositoryComponent,
    ParseStatus,
    normalize_repository_url,
)


@dataclass(frozen=True, slots=True)
class LegacyRepositoryMappingMetadata:
    original_url: str
    license_snapshot: LicenseSnapshot
    modifications_notice: str
    source_tag: str | None = None

    def __post_init__(self) -> None:
        if not self.original_url.startswith("https://") or len(self.original_url) > 2_000:
            raise ValueError("legacy_mapping_original_url_invalid")
        if not self.modifications_notice.strip() or len(self.modifications_notice) > 2_000:
            raise ValueError("legacy_mapping_modifications_notice_invalid")


class LegacyRepositoryDraftMapper:
    """Map without synthesizing missing content or changing review state."""

    parser_name = "deterministic-card-composer"

    def map(
        self,
        draft: ReviewDraft,
        metadata: LegacyRepositoryMappingMetadata,
    ) -> ParsedRepositoryComponent:
        source = draft.artifact.source
        if source.source_url is None or source.source_path is None:
            raise ValueError("legacy_mapping_source_locator_missing")
        if source.source_revision is None:
            raise ValueError("legacy_mapping_source_revision_missing")
        repository_url = normalize_repository_url(source.source_url)
        fields: dict[str, object] = {}
        provenance: dict[str, tuple[FieldProvenance, ...]] = {}
        _add(fields, provenance, "title", draft.title.value, draft.title.evidence)
        if draft.aliases:
            _add(
                fields,
                provenance,
                "aliases",
                [item.value for item in draft.aliases],
                tuple(evidence for item in draft.aliases for evidence in item.evidence),
            )
        if draft.manufacturer is not None:
            _add(
                fields,
                provenance,
                "manufacturer",
                draft.manufacturer.value,
                draft.manufacturer.evidence,
            )
        if draft.selected_category is not None:
            _add(
                fields,
                provenance,
                "category_hint",
                draft.selected_category,
                draft.title.evidence,
            )
        if draft.summary is not None:
            _add(fields, provenance, "summary", draft.summary.value, draft.summary.evidence)
        if draft.detailed_description:
            _add(
                fields,
                provenance,
                "description",
                "\n\n".join(item.body for item in draft.detailed_description),
                tuple(
                    evidence for item in draft.detailed_description for evidence in item.evidence
                ),
            )
        if draft.features:
            _add(
                fields,
                provenance,
                "features",
                [item.value for item in draft.features],
                tuple(evidence for item in draft.features for evidence in item.evidence),
            )
        if draft.applications:
            _add(
                fields,
                provenance,
                "applications",
                [item.value for item in draft.applications],
                tuple(evidence for item in draft.applications for evidence in item.evidence),
            )
        if draft.module_specifications:
            _add(
                fields,
                provenance,
                "specifications",
                [
                    {
                        "key": item.taxonomy_path or item.label,
                        "label": item.label,
                        "value": item.value,
                        "unit": item.unit,
                        "review_required": item.review.review_required,
                    }
                    for item in draft.module_specifications
                ],
                tuple(
                    evidence for item in draft.module_specifications for evidence in item.evidence
                ),
            )
        if draft.module_connection.instructions:
            _add(
                fields,
                provenance,
                "usage_notes",
                "\n\n".join(item.body for item in draft.module_connection.instructions),
                tuple(
                    evidence
                    for item in draft.module_connection.instructions
                    for evidence in item.evidence
                ),
            )
        if draft.module_connection.pins:
            _add(
                fields,
                provenance,
                "module_pinout",
                [
                    {
                        "number": item.number,
                        "name": item.name,
                        "function": item.function,
                    }
                    for item in draft.module_connection.pins
                ],
                tuple(
                    evidence for item in draft.module_connection.pins for evidence in item.evidence
                ),
            )
        if draft.internal_electronic_components:
            _add(
                fields,
                provenance,
                "internal_electronic_components",
                [item.as_dict() for item in draft.internal_electronic_components],
                tuple(
                    evidence
                    for item in draft.internal_electronic_components
                    for evidence in item.evidence
                ),
            )
        if draft.kicad_symbols:
            _add(
                fields,
                provenance,
                "kicad_symbols",
                [item.as_dict() for item in draft.kicad_symbols],
                tuple(
                    evidence for item in draft.kicad_symbols for evidence in item.source_evidence
                ),
            )
        if draft.resources:
            _add(
                fields,
                provenance,
                "resources",
                [
                    {"label": item.label, "url": item.locator, "kind": item.kind.value}
                    for item in draft.resources
                ],
                tuple(evidence for item in draft.resources for evidence in item.evidence),
            )
        warnings = tuple(item.code for item in draft.review_warnings)
        return ParsedRepositoryComponent(
            source_key=source.source_key,
            repository_url=repository_url,
            source_revision=source.source_revision,
            source_tag=metadata.source_tag,
            source_file_path=source.source_path,
            source_entry_name=None,
            original_url=metadata.original_url,
            parser_name=self.parser_name,
            parser_version=draft.composer_version,
            parsed_at=draft.composed_at,
            status=ParseStatus.PARSED_WITH_WARNINGS if warnings else ParseStatus.PARSED,
            normalized_fields=fields,
            provenance=provenance,
            license_snapshot=metadata.license_snapshot,
            modifications_notice=metadata.modifications_notice,
            warnings=warnings,
        )


def _add(
    fields: dict[str, object],
    provenance: dict[str, tuple[FieldProvenance, ...]],
    key: str,
    value: object,
    evidence: tuple[EvidenceFragment, ...],
) -> None:
    unique = tuple(dict.fromkeys(evidence))
    if not unique:
        raise ValueError("legacy_mapping_field_provenance_missing")
    fields[key] = value
    provenance[key] = tuple(dict.fromkeys(_legacy_provenance(item) for item in unique))


def _legacy_provenance(evidence: EvidenceFragment) -> FieldProvenance:
    source = evidence.source
    if source.source_url is None or source.source_path is None or source.source_revision is None:
        raise ValueError("legacy_mapping_evidence_source_incomplete")
    return FieldProvenance(
        repository_url=normalize_repository_url(source.source_url),
        source_revision=source.source_revision,
        source_file_path=source.source_path,
        section_or_property=evidence.section or evidence.selector or "source",
        confidence=Confidence.HIGH,
        transformation=f"{evidence.extraction_method}:{evidence.parser_version}",
    )


def legacy_confidence(value: DraftConfidence) -> Confidence:
    """Keep the confidence vocabulary aligned for compatibility clients."""
    return {
        DraftConfidence.HIGH: Confidence.HIGH,
        DraftConfidence.MEDIUM: Confidence.MEDIUM,
        DraftConfidence.LOW: Confidence.LOW,
    }[value]
