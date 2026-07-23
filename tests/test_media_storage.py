"""Private bucket provisioning policy tests."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from arduino_component_kb.config import Settings
from arduino_component_kb.media.storage import MinioStorage


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
    )


async def test_provisioning_creates_missing_buckets_and_requires_no_public_policy() -> None:
    storage = MinioStorage(settings())
    client = Mock()
    client.bucket_exists.side_effect = [False, True]
    client.get_bucket_policy.return_value = ""
    storage.client = client

    await storage.ensure_private_buckets()

    client.make_bucket.assert_called_once_with("ackb-media-quarantine")
    assert client.get_bucket_policy.call_count == 2


async def test_provisioning_fails_closed_when_bucket_has_a_policy() -> None:
    storage = MinioStorage(settings())
    client = Mock()
    client.bucket_exists.return_value = True
    client.get_bucket_policy.return_value = '{"Statement": [{"Effect": "Allow"}]}'
    storage.client = client

    with pytest.raises(RuntimeError, match="private default required"):
        await storage.ensure_private_buckets()


async def test_object_listing_is_bounded_and_ignores_directories() -> None:
    storage = MinioStorage(settings())
    client = Mock()
    directory = Mock(is_dir=True, object_name="prefix/", last_modified=datetime.now(UTC))
    first = Mock(is_dir=False, object_name="first.bin", last_modified=datetime.now(UTC))
    second = Mock(is_dir=False, object_name="second.bin", last_modified=datetime.now(UTC))
    client.list_objects.return_value = iter((directory, first, second))
    storage.client = client

    objects = await storage.list_objects("ackb-media-quarantine", max_items=1)

    assert [item.object_key for item in objects] == ["first.bin"]
    client.list_objects.assert_called_once_with("ackb-media-quarantine", recursive=True)


async def test_presigned_urls_are_rewritten_to_same_origin_without_changing_signature() -> None:
    storage = MinioStorage(settings())
    client = Mock()
    client.presigned_put_object.return_value = (
        "http://minio:9000/ackb-media-quarantine/image.png?X-Amz-Signature=put"
    )
    client.presigned_get_object.return_value = (
        "http://minio:9000/ackb-media-variants/image.webp?X-Amz-Signature=get"
    )
    storage.client = client

    upload = await storage.presigned_put("ackb-media-quarantine", "image.png", 60)
    download = await storage.presigned_get("ackb-media-variants", "image.webp", 60)

    assert upload == ("/media-storage/ackb-media-quarantine/image.png?X-Amz-Signature=put")
    assert download == ("/media-storage/ackb-media-variants/image.webp?X-Amz-Signature=get")
    assert "minio:9000" not in upload
    assert "minio:9000" not in download
