"""Stage 2 HTTP contracts for multiple component images."""

from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from arduino_component_kb.api.catalog import (
    ComponentImagesUpdateRequest,
    ComponentMediaResponse,
)
from arduino_component_kb.api.media import UploadReservationRequest
from arduino_component_kb.config import Settings
from arduino_component_kb.main import create_app


class FakeDatabase:
    async def ping(self) -> None:
        return None

    async def dispose(self) -> None:
        return None


def test_openapi_exposes_workspace_and_snapshot_media_contracts() -> None:
    app = create_app(
        Settings(
            _env_file=None,
            environment="test",
            database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        ),
        FakeDatabase(),
    )
    schema = cast(dict[str, object], app.openapi())
    components = cast(
        dict[str, dict[str, object]],
        cast(dict[str, object], schema["components"])["schemas"],
    )
    for name in ("ComponentResponse", "PublicComponentResponse"):
        required = cast(list[str], components[name]["required"])
        assert "media" in required
    media_required = cast(list[str], components["ComponentMediaResponse"]["required"])
    assert {
        "asset_id",
        "purpose",
        "alt_text",
        "display_order",
        "is_primary",
        "variants",
    }.issubset(media_required)
    paths = cast(dict[str, object], schema["paths"])
    mutation = cast(dict[str, object], paths["/api/v1/workspace/components/{component_id}/images"])
    assert set(mutation) == {"put"}


def test_image_collection_request_is_bounded_and_revisioned() -> None:
    item = {
        "asset_id": str(uuid4()),
        "purpose": "product",
        "alt_text": "Top view",
        "caption": "Primary image",
    }
    payload = ComponentImagesUpdateRequest(
        revision=3,
        images=[item],
        primary_asset_id=item["asset_id"],
    )
    assert payload.revision == 3
    assert payload.images[0].domain().alt_text == "Top view"
    with pytest.raises(ValidationError):
        ComponentImagesUpdateRequest(
            revision=3,
            images=[{**item, "asset_id": str(uuid4())} for _ in range(13)],
        )


def test_attached_upload_requires_an_explicit_component_revision_in_service_contract() -> None:
    request = UploadReservationRequest(
        component_id=uuid4(),
        component_revision=7,
        purpose="detail",
        alt_text="Connector detail",
        declared_mime="image/png",
        declared_size_bytes=1024,
    )
    assert request.component_revision == 7


def test_media_response_never_contains_storage_identifiers() -> None:
    fields = set(ComponentMediaResponse.model_fields)
    assert {"bucket", "object_key", "original_url"}.isdisjoint(fields)
