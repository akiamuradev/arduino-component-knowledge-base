"""Async boundary around the synchronous official MinIO client."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from io import BytesIO
from pathlib import Path
from typing import Protocol, TypeVar

from anyio import to_thread
from minio import Minio
from minio.error import S3Error

from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import MAX_IMAGE_BYTES

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ObjectMetadata:
    size: int
    content_type: str | None


@dataclass(frozen=True, slots=True)
class StorageObject:
    object_key: str
    last_modified: datetime


class MediaStorage(Protocol):
    async def presigned_put(self, bucket: str, object_key: str, expires_seconds: int) -> str: ...
    async def stat(self, bucket: str, object_key: str) -> ObjectMetadata: ...
    async def download(
        self, bucket: str, object_key: str, max_bytes: int = MAX_IMAGE_BYTES
    ) -> bytes: ...
    async def download_to_file(
        self, bucket: str, object_key: str, destination: Path, max_bytes: int
    ) -> None: ...
    async def upload(
        self, bucket: str, object_key: str, data: bytes, content_type: str
    ) -> None: ...
    async def upload_file(
        self, bucket: str, object_key: str, source: Path, content_type: str
    ) -> None: ...
    async def delete(self, bucket: str, object_key: str) -> None: ...
    async def list_objects(self, bucket: str, max_items: int) -> tuple[StorageObject, ...]: ...


class MinioStorage:
    """Keep binary bytes in private MinIO buckets, never in PostgreSQL."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key.get_secret_value(),
            secret_key=settings.minio_secret_key.get_secret_value(),
            secure=settings.minio_secure,
        )

    async def _run(self, function: Callable[[], T]) -> T:
        return await to_thread.run_sync(function)

    async def ensure_private_buckets(self) -> None:
        for bucket in (
            self.settings.minio_quarantine_bucket,
            self.settings.minio_variants_bucket,
        ):
            exists = await self._run(partial(self.client.bucket_exists, bucket))
            if not exists:
                await self._run(partial(self.client.make_bucket, bucket))
            try:
                policy = await self._run(partial(self.client.get_bucket_policy, bucket))
            except S3Error as error:
                if error.code != "NoSuchBucketPolicy":
                    raise
            else:
                if policy.strip():
                    raise RuntimeError(f"bucket {bucket!r} has a policy; private default required")

    async def presigned_put(self, bucket: str, object_key: str, expires_seconds: int) -> str:
        return await self._run(
            lambda: self.client.presigned_put_object(
                bucket,
                object_key,
                expires=timedelta(seconds=expires_seconds),
            )
        )

    async def stat(self, bucket: str, object_key: str) -> ObjectMetadata:
        result = await self._run(lambda: self.client.stat_object(bucket, object_key))
        if result.size is None:
            raise RuntimeError("MinIO returned object metadata without a size")
        return ObjectMetadata(size=result.size, content_type=result.content_type)

    async def download(
        self, bucket: str, object_key: str, max_bytes: int = MAX_IMAGE_BYTES
    ) -> bytes:
        def read() -> bytes:
            response = self.client.get_object(bucket, object_key)
            try:
                return response.read(max_bytes + 1)
            finally:
                response.close()
                response.release_conn()

        return await self._run(read)

    async def download_to_file(
        self, bucket: str, object_key: str, destination: Path, max_bytes: int
    ) -> None:
        def stream() -> None:
            response = self.client.get_object(bucket, object_key)
            total = 0
            try:
                with destination.open("xb") as output:
                    for chunk in response.stream(amt=1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise ValueError("object exceeds media byte limit")
                        output.write(chunk)
            finally:
                response.close()
                response.release_conn()

        await self._run(stream)

    async def upload(self, bucket: str, object_key: str, data: bytes, content_type: str) -> None:
        await self._run(
            lambda: self.client.put_object(
                bucket,
                object_key,
                BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
        )

    async def upload_file(
        self, bucket: str, object_key: str, source: Path, content_type: str
    ) -> None:
        await self._run(
            partial(
                self.client.fput_object,
                bucket,
                object_key,
                str(source),
                content_type=content_type,
            )
        )

    async def delete(self, bucket: str, object_key: str) -> None:
        await self._run(lambda: self.client.remove_object(bucket, object_key))

    async def list_objects(self, bucket: str, max_items: int) -> tuple[StorageObject, ...]:
        def collect() -> tuple[StorageObject, ...]:
            objects: list[StorageObject] = []
            for item in self.client.list_objects(bucket, recursive=True):
                if item.is_dir or item.object_name is None or item.last_modified is None:
                    continue
                objects.append(StorageObject(item.object_name, item.last_modified))
                if len(objects) >= max_items:
                    break
            return tuple(objects)

        return await self._run(collect)
