"""Private bucket provisioning policy tests."""

from __future__ import annotations

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
