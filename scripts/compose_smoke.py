"""HTTP smoke test for an already started Docker Compose stack."""

from __future__ import annotations

import json
import os
from urllib.parse import urljoin
from urllib.request import urlopen


def fetch(base_url: str, path: str) -> tuple[int, bytes]:
    with urlopen(urljoin(base_url, path), timeout=5) as response:  # noqa: S310
        return response.status, response.read(64 * 1024)


def main() -> int:
    base_url = os.environ.get("ACKB_SMOKE_BASE_URL", "http://127.0.0.1:8080/")
    health_status, health_body = fetch(base_url, "health")
    ready_status, ready_body = fetch(base_url, "ready")
    frontend_status, frontend_body = fetch(base_url, "")
    assert health_status == 200
    assert json.loads(health_body)["status"] == "ok"
    assert ready_status == 200
    assert json.loads(ready_body)["status"] == "ready"
    assert frontend_status == 200
    assert b'<div id="root">' in frontend_body
    print("Docker Compose HTTP smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
