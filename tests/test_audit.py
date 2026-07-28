"""Protected audit-journal contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.audit import _aware, _response, router
from arduino_component_kb.auth.domain import AuditRecord
from arduino_component_kb.auth.repository import AuthRepository, safe_audit_details


def test_safe_audit_details_accepts_only_reviewed_bounded_metadata() -> None:
    details = {
        "revision": 4,
        "roles": ["student", "editor"],
        "editor_expires_at": "2026-08-20T12:00:00+00:00",
        "reset": False,
    }

    assert safe_audit_details(details) == details


@pytest.mark.parametrize("field", ["password", "token", "secret", "authorization"])
def test_safe_audit_details_rejects_secret_bearing_fields(field: str) -> None:
    with pytest.raises(ValueError, match="unsupported field"):
        safe_audit_details({field: "must-never-be-persisted"})


@pytest.mark.parametrize(
    "details",
    [
        {"reason": "x" * 201},
        {"roles": ["student"] * 17},
        {"summary": {"nested": "value"}},
    ],
)
def test_safe_audit_details_rejects_unbounded_or_nested_values(
    details: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="unsupported value"):
        safe_audit_details(details)


async def test_audit_repository_builds_exact_bounded_filter_query() -> None:
    actor_id = uuid4()
    occurred_from = datetime(2026, 7, 1, tzinfo=UTC)
    occurred_to = occurred_from + timedelta(days=7)
    rows = Mock()
    rows.all.return_value = []
    session = Mock(spec=AsyncSession)
    session.execute = AsyncMock(return_value=rows)
    session.scalar = AsyncMock(return_value=7)
    repository = AuthRepository(cast(AsyncSession, session))

    records, total = await repository.list_audit_events(
        actor_user_id=actor_id,
        action="component.published",
        occurred_from=occurred_from,
        occurred_to=occurred_to,
        limit=50,
        offset=100,
    )

    assert records == ()
    assert total == 7
    execute_call = session.execute.await_args
    assert execute_call is not None
    sql = str(execute_call.args[0])
    assert "LEFT OUTER JOIN users ON users.id = audit_events.actor_user_id" in sql
    assert "audit_events.actor_user_id =" in sql
    assert "audit_events.action =" in sql
    assert "audit_events.occurred_at >=" in sql
    assert "audit_events.occurred_at <" in sql
    assert "ORDER BY audit_events.occurred_at DESC, audit_events.id DESC" in sql
    assert "LIMIT" in sql
    assert "OFFSET" in sql


def test_public_audit_projection_excludes_internal_details_and_request_id() -> None:
    record = AuditRecord(
        id=uuid4(),
        occurred_at=datetime(2026, 7, 29, 12, 0, tzinfo=UTC),
        actor_user_id=uuid4(),
        actor_type="user",
        actor_login="administrator",
        actor_display_name="Администратор",
        action="component.published",
        object_type="component",
        object_id=UUID(int=3),
        outcome="success",
    )

    payload = _response(record).model_dump(mode="json")

    assert set(payload) == {"id", "occurred_at", "actor", "action", "object", "outcome"}
    assert set(payload["actor"]) == {"id", "type", "login", "display_name"}
    assert set(payload["object"]) == {"type", "id"}
    assert "details_safe_json" not in payload
    assert "request_id" not in payload


def test_audit_dates_must_include_a_timezone() -> None:
    with pytest.raises(HTTPException) as raised:
        _aware(datetime(2026, 7, 29, 12, 0))

    assert raised.value.status_code == 422
    detail = cast(object, raised.value.detail)
    assert detail == {"code": "audit_date_range_invalid"}


def test_audit_router_has_no_mutation_operation() -> None:
    methods = {method for route in router.routes for method in getattr(route, "methods", set())}

    assert methods == {"GET"}
