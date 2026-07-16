"""Dramatiq actor for durable parser imports."""

from __future__ import annotations

import asyncio
from uuid import UUID

import dramatiq

from arduino_component_kb.broker import settings
from arduino_component_kb.imports.domain import RetryableImportError
from arduino_component_kb.imports.processor import process_import_job


@dramatiq.actor(
    queue_name="imports",
    max_retries=settings.import_job_max_attempts - 1,
    min_backoff=5_000,
    max_backoff=60_000,
)
def process_import(job_id: str) -> None:
    try:
        asyncio.run(process_import_job(UUID(job_id), settings))
    except RetryableImportError as error:
        raise dramatiq.Retry(delay=error.delay_ms) from error
