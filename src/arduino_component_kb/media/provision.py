"""Provision the two required MinIO buckets with private-default access."""

from __future__ import annotations

import asyncio

from arduino_component_kb.config import Settings
from arduino_component_kb.media.storage import MinioStorage


def main() -> int:
    asyncio.run(MinioStorage(Settings()).ensure_private_buckets())
    print("Private MinIO media buckets are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
