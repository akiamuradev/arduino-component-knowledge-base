"""Dramatiq image actors. Import this module only with complete ACKB settings."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast
from uuid import UUID

import dramatiq
from dramatiq.broker import Broker
from dramatiq.brokers.redis import RedisBroker

from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import RetryableJobError
from arduino_component_kb.media.processor import process_media_job
from arduino_component_kb.media.video_processor import process_video_job

settings = Settings()
broker_factory = cast(Callable[..., Broker], RedisBroker)
dramatiq.set_broker(broker_factory(url=settings.redis_url))


@dramatiq.actor(
    queue_name="images",
    max_retries=settings.media_job_max_attempts - 1,
    min_backoff=5_000,
    max_backoff=60_000,
)
def process_media_image(job_id: str) -> None:
    """Run one async image job in a bounded worker process."""
    try:
        asyncio.run(process_media_job(UUID(job_id), settings))
    except RetryableJobError as error:
        raise dramatiq.Retry(delay=error.delay_ms) from error


@dramatiq.actor(
    queue_name="videos",
    max_retries=settings.media_job_max_attempts - 1,
    min_backoff=15_000,
    max_backoff=120_000,
)
def process_media_video(job_id: str) -> None:
    """Run one bounded local FFmpeg job."""
    try:
        asyncio.run(process_video_job(UUID(job_id), settings))
    except RetryableJobError as error:
        raise dramatiq.Retry(delay=error.delay_ms) from error
