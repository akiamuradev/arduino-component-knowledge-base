"""Dramatiq/Redis queue adapter for image jobs."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

import dramatiq
from dramatiq.broker import Broker
from dramatiq.brokers.redis import RedisBroker

from arduino_component_kb.config import Settings
from arduino_component_kb.media.domain import MediaKind


class DramatiqMediaQueue:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        broker_factory = cast(Callable[..., Broker], RedisBroker)
        dramatiq.set_broker(broker_factory(url=settings.redis_url))

    def enqueue(self, job_id: UUID, kind: MediaKind) -> None:
        from arduino_component_kb.media.tasks import process_media_image, process_media_video

        actor = process_media_image if kind is MediaKind.IMAGE else process_media_video
        actor.send(str(job_id))
