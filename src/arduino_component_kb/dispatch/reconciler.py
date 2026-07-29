"""Bounded delivery reconciler for PostgreSQL-backed background jobs."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.dispatch.repository import DispatchIntent, DispatchRepository
from arduino_component_kb.logging import configure_logging

logger = logging.getLogger("arduino_component_kb.dispatch")


class DispatchPublisher(Protocol):
    def publish(self, intent: DispatchIntent) -> None: ...


class DramatiqDispatchPublisher:
    """Publish only opaque job identifiers to the configured shared broker."""

    def publish(self, intent: DispatchIntent) -> None:
        from arduino_component_kb.worker import (
            process_import,
            process_media_image,
            process_media_video,
        )

        if intent.queue_name == "imports":
            process_import.send(str(intent.job_id))
        elif intent.queue_name == "images":
            process_media_image.send(str(intent.job_id))
        else:
            process_media_video.send(str(intent.job_id))


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    recovered: int
    claimed: int
    delivered: int
    failed: int


def publish_safely(publisher: DispatchPublisher, intent: DispatchIntent) -> bool:
    try:
        publisher.publish(intent)
    except Exception as error:
        logger.warning(
            "job_dispatch_failed",
            extra={
                "dispatch_id": str(intent.id),
                "job_type": intent.job_type,
                "queue_name": intent.queue_name,
                "attempt": intent.attempt,
                "error_type": type(error).__name__,
            },
        )
        return False
    return True


async def reconcile_once(
    settings: Settings,
    publisher: DispatchPublisher | None = None,
    *,
    now: datetime | None = None,
) -> ReconcileResult:
    """Recover lost deliveries and publish one bounded batch."""
    current_time = now or datetime.now(UTC)
    database = Database(settings)
    resolved_publisher = publisher or DramatiqDispatchPublisher()
    try:
        async with database.sessions() as session:
            repository = DispatchRepository(session)
            async with session.begin():
                recovered = await repository.recover_lost_deliveries(
                    now=current_time,
                    stale_delivery_seconds=settings.job_dispatch_stale_seconds,
                    import_lease_seconds=settings.import_lock_ttl_seconds,
                    media_lease_seconds=settings.media_job_lease_seconds,
                    limit=settings.job_dispatch_batch_size,
                )
                intents = await repository.claim_due(
                    now=current_time,
                    limit=settings.job_dispatch_batch_size,
                    claim_lease_seconds=settings.job_dispatch_claim_lease_seconds,
                )

        delivered = 0
        failed = 0
        for intent in intents:
            attempt_time = datetime.now(UTC)
            if not publish_safely(resolved_publisher, intent):
                failed += 1
                async with database.sessions() as session:
                    async with session.begin():
                        await DispatchRepository(session).mark_delivery_failed(
                            intent.id, attempt_time
                        )
            else:
                delivered += 1
                async with database.sessions() as session:
                    async with session.begin():
                        await DispatchRepository(session).mark_delivered(intent.id, attempt_time)
        result = ReconcileResult(
            recovered=recovered,
            claimed=len(intents),
            delivered=delivered,
            failed=failed,
        )
        logger.info(
            "job_dispatch_reconciled",
            extra={
                "recovered": result.recovered,
                "claimed": result.claimed,
                "delivered": result.delivered,
                "failed": result.failed,
            },
        )
        return result
    finally:
        await database.dispose()


async def reconcile_forever(settings: Settings) -> None:
    while True:
        await reconcile_once(settings)
        await asyncio.sleep(settings.job_dispatch_interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile durable background-job delivery")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="run continuously; without this flag exactly one bounded batch is processed",
    )
    arguments = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    if arguments.loop:
        asyncio.run(reconcile_forever(settings))
    else:
        result = asyncio.run(reconcile_once(settings))
        print(
            f"recovered={result.recovered} claimed={result.claimed} "
            f"delivered={result.delivered} failed={result.failed}"
        )
