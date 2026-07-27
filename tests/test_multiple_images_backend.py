"""Stage 2 HTTP contracts for multiple component images."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from arduino_component_kb.api.catalog import (
    ComponentImagesUpdateRequest,
    ComponentMediaResponse,
    PublicComponentMediaResponse,
    public_component_media_response,
)
from arduino_component_kb.api.media import UploadReservationRequest
from arduino_component_kb.config import Settings
from arduino_component_kb.main import create_app
from arduino_component_kb.media.domain import (
    ComponentMedia,
    ComponentMediaVariant,
    MediaKind,
    MediaStatus,
)
from arduino_component_kb.media.repository import MediaRepository
from arduino_component_kb.media.storage import MediaStorage


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
    public_media_required = cast(
        list[str],
        components["PublicComponentMediaResponse"]["required"],
    )
    assert {"asset_id", "alt_text", "is_primary", "variants"}.issubset(public_media_required)
    public_variant_required = cast(
        list[str],
        components["PublicComponentMediaVariantResponse"]["required"],
    )
    assert "url" in public_variant_required
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
    for response_type in (ComponentMediaResponse, PublicComponentMediaResponse):
        fields = set(response_type.model_fields)
        assert {"bucket", "object_key", "original_url"}.isdisjoint(fields)


async def test_public_media_signs_only_snapshot_verified_processed_variant() -> None:
    asset_id = uuid4()
    item = ComponentMedia(
        asset_id=asset_id,
        kind=MediaKind.IMAGE,
        purpose="product",
        alt_text="Published top view",
        caption="Immutable caption",
        display_order=0,
        is_primary=True,
        status=MediaStatus.READY,
        width=1600,
        height=1200,
        variants=(
            ComponentMediaVariant(
                name="320w",
                mime="image/webp",
                width=320,
                height=240,
                sha256="1" * 64,
            ),
        ),
    )
    row = SimpleNamespace(
        variant="320w",
        bucket="ackb-media-variants",
        object_key=f"images/{asset_id}/320w.webp",
        mime="image/webp",
        width=320,
        height=240,
        sha256="1" * 64,
    )
    repository = Mock(spec=MediaRepository)
    repository.get_asset = AsyncMock(return_value=SimpleNamespace(status="ready", kind="image"))
    repository.variants = AsyncMock(return_value=[row])
    storage = Mock(spec=MediaStorage)
    storage.presigned_get = AsyncMock(return_value="/media-storage/variants/320w.webp?signed=1")

    projected = await public_component_media_response(
        item,
        cast(MediaRepository, repository),
        cast(MediaStorage, storage),
        600,
    )

    assert projected is not None
    assert projected.alt_text == "Published top view"
    assert projected.caption == "Immutable caption"
    assert projected.variants[0].url.startswith("/media-storage/")
    storage.presigned_get.assert_awaited_once_with(
        "ackb-media-variants",
        f"images/{asset_id}/320w.webp",
        600,
    )
    rendered = projected.model_dump_json()
    assert "object_key" not in rendered
    assert "ackb-media-variants" not in rendered


async def test_public_media_fails_closed_when_variant_changed_after_snapshot() -> None:
    asset_id = uuid4()
    item = ComponentMedia(
        asset_id=asset_id,
        kind=MediaKind.IMAGE,
        purpose="product",
        alt_text="Published top view",
        caption=None,
        display_order=0,
        is_primary=True,
        status=MediaStatus.READY,
        width=320,
        height=240,
        variants=(
            ComponentMediaVariant(
                name="320w",
                mime="image/webp",
                width=320,
                height=240,
                sha256="1" * 64,
            ),
        ),
    )
    repository = Mock(spec=MediaRepository)
    repository.get_asset = AsyncMock(return_value=SimpleNamespace(status="ready", kind="image"))
    repository.variants = AsyncMock(
        return_value=[
            SimpleNamespace(
                variant="320w",
                bucket="ackb-media-variants",
                object_key="changed.webp",
                mime="image/webp",
                width=320,
                height=240,
                sha256="2" * 64,
            )
        ]
    )
    storage = Mock(spec=MediaStorage)
    storage.presigned_get = AsyncMock()

    assert (
        await public_component_media_response(
            item,
            cast(MediaRepository, repository),
            cast(MediaStorage, storage),
            600,
        )
        is None
    )
    storage.presigned_get.assert_not_awaited()
