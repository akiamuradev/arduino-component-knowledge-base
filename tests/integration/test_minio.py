"""Real MinIO object lifecycle and private-bucket integration tests."""

from __future__ import annotations

from uuid import uuid4

import pytest
from minio.error import S3Error

from arduino_component_kb.config import Settings
from arduino_component_kb.media.storage import MinioStorage

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_private_minio_upload_metadata_download_and_presign(
    integration_settings: Settings,
) -> None:
    storage = MinioStorage(integration_settings)
    await storage.ensure_private_buckets()
    bucket = integration_settings.minio_quarantine_bucket
    object_key = f"integration/{uuid4().hex}.png"
    payload = b"\x89PNG\r\n\x1a\n-integration-object"
    try:
        await storage.upload(bucket, object_key, payload, "image/png")
        metadata = await storage.stat(bucket, object_key)
        assert metadata.size == len(payload)
        assert metadata.content_type == "image/png"
        assert await storage.download(bucket, object_key, max_bytes=len(payload)) == payload
        presigned = await storage.presigned_put(bucket, f"integration/{uuid4().hex}.png", 60)
        assert object_key not in presigned
        assert "X-Amz-Signature=" in presigned
        with pytest.raises(S3Error) as policy_error:
            await storage._run(lambda: storage.client.get_bucket_policy(bucket))
        assert policy_error.value.code == "NoSuchBucketPolicy"
    finally:
        await storage.delete(bucket, object_key)
