"""Stage 12 API projection and route contracts."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError

from arduino_component_kb.api.dependencies import csrf_principal
from arduino_component_kb.api.import_reviews import (
    _review_error,
    _workspace,
)
from arduino_component_kb.api.import_reviews import (
    router as import_review_router,
)
from arduino_component_kb.auth.domain import Role
from arduino_component_kb.config import Settings
from arduino_component_kb.imports.persistence_models import (
    ComponentEnrichmentRecord,
    ComponentIdentityCandidateRecord,
    ImportPipelineArtifact,
    ImportReviewDraftRecord,
    ParserEvaluationRecord,
)
from arduino_component_kb.imports.review import (
    ImportReviewBundle,
    unmapped_specification_key,
)
from arduino_component_kb.main import create_app

DRAFT_ID = UUID("11111111-2222-4333-8444-555555555555")
ARTIFACT_ID = UUID("22222222-3333-4444-8555-666666666666")
IDENTITY_ID = UUID("33333333-4444-4555-8666-777777777777")
EVALUATION_ID = UUID("44444444-5555-4666-8777-888888888888")
ENRICHMENT_ID = UUID("55555555-6666-4777-8888-999999999999")
NOW = datetime(2026, 7, 23, 12, 0, tzinfo=UTC)


class FakeDatabase:
    async def ping(self) -> None:
        return None

    async def dispose(self) -> None:
        return None


def _dependency_calls(dependant: Dependant) -> Iterator[Callable[..., object]]:
    for child in dependant.dependencies:
        if child.call is not None:
            yield child.call
        yield from _dependency_calls(child)


def test_workspace_projection_exposes_evidence_and_keeps_pinout_levels_separate() -> None:
    unmapped: dict[str, object] = {
        "original_label": "Peak channel behavior",
        "original_value": "1.2 A",
        "raw_value": "1.2 A",
        "reason": "taxonomy_alias_missing",
        "evidence": [{"section": "Specifications", "parser_version": "2.0.0"}],
    }
    draft = ImportReviewDraftRecord(
        id=DRAFT_ID,
        artifact_id=ARTIFACT_ID,
        identity_candidate_id=IDENTITY_ID,
        parser_evaluation_id=EVALUATION_ID,
        component_id=None,
        input_sha256="a" * 64,
        payload_sha256="b" * 64,
        payload={
            "title": {
                "value": "Grove Motor Driver",
                "review": {"confidence": "high"},
            },
            "summary": {
                "value": "A module",
                "review": {"confidence": "medium"},
            },
            "module_specifications": [],
            "module_connection": {
                "pins": [{"number": "1", "name": "VCC", "function": "Module supply"}],
                "instructions": [],
            },
            "internal_electronic_components": [{"record_id": "Driver:DRV8830", "name": "DRV8830"}],
            "kicad_symbols": [
                {
                    "record_id": "Driver:DRV8830",
                    "pinout_level": "kicad_symbol",
                    "pins": [{"number": "4", "name": "GND"}],
                }
            ],
            "provenance": [{"section": "Overview", "parser_version": "2.0.0"}],
            "quality_score_basis_points": 920,
            "artifact": {"source": {"source_key": "seeed_wiki"}},
        },
        schema_version="review-draft/v1",
        composer_version="1.0.0",
        quality_route="manual_review",
        created_at=NOW,
    )
    artifact = ImportPipelineArtifact(
        id=ARTIFACT_ID,
        source_id=UUID("00000000-0000-4000-9000-000000000004"),
        component_id=None,
        run_id=UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        source_key="seeed_wiki",
        source_url="https://example.invalid/source",
        source_file_path="module.md",
        source_revision="c" * 40,
        content_sha256="d" * 64,
        facts_sha256="e" * 64,
        facts_payload={
            "artifact": {"source": {"source_key": "seeed_wiki"}},
            "unmapped_specifications": [unmapped],
            "conflicts": [{"taxonomy_path": "electrical.current.maximum"}],
        },
        parser_version="2.0.0",
        normalization_version="1.0.0",
        idempotency_key="artifact",
        created_at=NOW,
    )
    identity = ComponentIdentityCandidateRecord(
        id=IDENTITY_ID,
        artifact_id=ARTIFACT_ID,
        payload_sha256="f" * 64,
        payload={"score_breakdown": [{"rule_id": "module_keyword"}], "evidence": []},
        canonical_name="Grove Motor Driver",
        component_kind="module",
        selected_category="actuators",
        confidence="high",
        resolution_status="auto_resolved",
        resolver_version="2.0.0",
        created_at=NOW,
    )
    evaluation = ParserEvaluationRecord(
        id=EVALUATION_ID,
        artifact_id=ARTIFACT_ID,
        identity_candidate_id=IDENTITY_ID,
        input_sha256="1" * 64,
        report_sha256="2" * 64,
        payload={"overall_score_basis_points": 920, "route": "manual_review", "issues": []},
        route="manual_review",
        score_basis_points=920,
        evaluator_version="1.0.0",
        created_at=NOW,
    )
    enrichment = ComponentEnrichmentRecord(
        id=ENRICHMENT_ID,
        artifact_id=ARTIFACT_ID,
        review_draft_id=DRAFT_ID,
        component_id=None,
        provider="kicad",
        relation_type="main_integrated_circuit",
        external_identity="Driver:DRV8830",
        payload={
            "relation": {
                "score_breakdown": [{"rule_id": "part_number", "weight_basis_points": 950}],
                "symbol": {"symbol_name": "DRV8830", "pins": [{"number": "4", "name": "GND"}]},
            },
            "review_reasons": ["internal_relation_requires_review"],
        },
        payload_sha256="3" * 64,
        confidence_basis_points=950,
        status="suggested",
        parser_version="1.0.0",
        source_revision="4" * 40,
        evidence=[{"section": "Specifications", "parser_version": "2.0.0"}],
        reviewed_by=None,
        reviewed_at=None,
        created_at=NOW,
        updated_at=NOW,
    )
    response = _workspace(
        ImportReviewBundle(
            draft,
            artifact,
            evaluation,
            (identity,),
            (enrichment,),
            None,
            (),
        )
    )

    assert response.field_confidence == {"title": "high", "summary": "medium"}
    assert response.identity_candidates[0].evidence["score_breakdown"]
    assert response.enrichments[0].score_breakdown
    assert response.unmapped_specifications[0].key == unmapped_specification_key(unmapped)
    assert response.conflicts
    assert "pins" in response.module_connection
    assert "pins" not in response.internal_electronic_components[0]
    assert response.kicad_symbols[0]["pinout_level"] == "kicad_symbol"


def test_stage_12_openapi_has_all_review_actions_and_response_contract() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        ),
        FakeDatabase(),
    )
    paths = {route.path for route in import_review_router.routes if isinstance(route, APIRoute)}
    assert paths == {
        "/api/v1/admin/import-reviews",
        "/api/v1/admin/import-reviews/{review_draft_id}",
        "/api/v1/admin/import-reviews/{review_draft_id}/enrichments/{enrichment_id}/decision",
        "/api/v1/admin/import-reviews/{review_draft_id}/enrichments/{enrichment_id}/relation",
        "/api/v1/admin/import-reviews/{review_draft_id}/identity",
        "/api/v1/admin/import-reviews/{review_draft_id}/specification-mappings",
        "/api/v1/admin/import-reviews/{review_draft_id}/parser-issues",
        "/api/v1/admin/import-reviews/{review_draft_id}/confirm",
    }
    schema = cast(dict[str, object], app.openapi())
    schemas = cast(dict[str, object], cast(dict[str, object], schema["components"])["schemas"])
    workspace = cast(dict[str, object], schemas["ImportReviewWorkspaceResponse"])
    required = set(cast(list[str], workspace["required"]))
    assert {
        "facts",
        "provenance",
        "field_confidence",
        "identity_candidates",
        "quality_report",
        "unmapped_specifications",
        "conflicts",
        "enrichments",
        "module_connection",
        "internal_electronic_components",
        "kicad_symbols",
        "audit_trail",
    }.issubset(required)


def test_stage_12_routes_preserve_administrator_rbac_and_csrf() -> None:
    checked_mutations = 0
    for route in import_review_router.routes:
        assert isinstance(route, APIRoute)
        calls = set(_dependency_calls(route.dependant))
        role_sets = {
            frozenset(roles)
            for call in calls
            if (roles := inspect.getclosurevars(call).nonlocals.get("allowed")) is not None
        }
        assert frozenset({Role.ADMINISTRATOR}) in role_sets
        if (route.methods or set()).intersection({"POST", "PUT", "PATCH", "DELETE"}):
            assert csrf_principal in calls
            checked_mutations += 1
    assert checked_mutations == 6


def test_database_conflict_is_returned_as_a_safe_stable_code() -> None:
    error = IntegrityError("secret statement", {}, RuntimeError("secret database detail"))
    response = _review_error(error)
    assert response.status_code == 409
    assert cast(object, response.detail) == {"code": "import_review_write_conflict"}
