"""Dedicated single-thread legacy queue; PostgreSQL owns retries and dispatch."""

import asyncio
from uuid import UUID

import dramatiq

from arduino_component_kb.broker import settings
from arduino_component_kb.legacy.processor import process_bundle


@dramatiq.actor(queue_name="legacy", max_retries=0, time_limit=1_500_000)
def process_legacy_bundle(bundle_id: str) -> None:
    asyncio.run(process_bundle(UUID(bundle_id), settings))
