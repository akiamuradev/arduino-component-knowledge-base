"""Duplicate review request and OpenAPI contract tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from arduino_component_kb.api.duplicates import DecisionRequest
from arduino_component_kb.config import Settings
from arduino_component_kb.main import create_app


def test_decision_contract_requires_reason_and_consistent_identifiers() -> None:
    survivor = uuid4()
    source = uuid4()
    request = DecisionRequest(
        decision="merge",
        left_revision=2,
        right_revision=3,
        survivor_component_id=survivor,
        field_sources={"title": source},
        reason="Карточки описывают одну модель",
    )
    assert request.survivor_component_id == survivor
    assert request.field_sources == {"title": source}
    with pytest.raises(ValidationError):
        DecisionRequest(
            decision="reject",
            left_revision=1,
            right_revision=1,
            reason="",
        )
    with pytest.raises(ValidationError):
        DecisionRequest(
            decision="attach",
            left_revision=1,
            right_revision=1,
            reason="Источник относится к существующей карточке",
        )


def test_openapi_exposes_admin_duplicate_review_only() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost:5432/ackb",
        )
    )
    paths = app.openapi()["paths"]
    assert "/api/v1/admin/duplicates" in paths
    assert "/api/v1/admin/duplicates/{candidate_id}" in paths
    assert "/api/v1/admin/duplicates/{candidate_id}/decision" in paths
    assert "post" in paths["/api/v1/admin/duplicates/{candidate_id}/decision"]
