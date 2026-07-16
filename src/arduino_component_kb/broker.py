"""One Redis broker shared by every Dramatiq actor module."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast

import dramatiq
from dramatiq.broker import Broker
from dramatiq.brokers.redis import RedisBroker

from arduino_component_kb.config import Settings

settings = Settings()
broker_factory = cast(Callable[..., Broker], RedisBroker)
broker = broker_factory(url=settings.redis_url)
dramatiq.set_broker(broker)
