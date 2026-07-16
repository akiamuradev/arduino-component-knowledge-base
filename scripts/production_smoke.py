"""Verify the deployed internal HTTPS edge without disabling certificate checks."""

from __future__ import annotations

import json
import os
import ssl
from http.client import HTTPMessage
from pathlib import Path
from typing import IO
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen

MAX_RESPONSE_BYTES = 64 * 1024


def validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("ACKB_SMOKE_BASE_URL must be an HTTPS origin on port 443")
    return value.rstrip("/") + "/"


def fetch(base_url: str, path: str, context: ssl.SSLContext) -> tuple[int, bytes, dict[str, str]]:
    request = Request(  # noqa: S310 - base_url is restricted to a validated HTTPS origin.
        urljoin(base_url, path), headers={"User-Agent": "ackb-production-smoke/1"}
    )
    with urlopen(request, timeout=10, context=context) as response:  # noqa: S310
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("smoke response exceeds byte limit")
        return response.status, body, dict(response.headers.items())


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: IO[bytes],
        code: int,
        message: str,
        headers: HTTPMessage,
        new_url: str,
    ) -> None:
        return None


def assert_http_redirect(base_url: str, context: ssl.SSLContext) -> None:
    hostname = urlsplit(base_url).hostname
    if hostname is None:
        raise ValueError("validated base URL lost its hostname")
    opener = build_opener(NoRedirect(), HTTPSHandler(context=context))
    try:
        opener.open(f"http://{hostname}/", timeout=10)  # noqa: S310
    except HTTPError as error:
        if error.code != 308 or error.headers.get("Location") != base_url:
            raise AssertionError("HTTP endpoint did not return the exact HTTPS redirect") from error
    else:
        raise AssertionError("HTTP endpoint did not redirect to HTTPS")


def main() -> int:
    base_url = validated_base_url(os.environ["ACKB_SMOKE_BASE_URL"])
    ca_file = Path(os.environ["ACKB_SMOKE_CA_FILE"])
    if not ca_file.is_file():
        raise FileNotFoundError("ACKB_SMOKE_CA_FILE is not a readable file")
    context = ssl.create_default_context(cafile=str(ca_file))

    health_status, health_body, health_headers = fetch(base_url, "health", context)
    ready_status, ready_body, _ = fetch(base_url, "ready", context)
    frontend_status, frontend_body, frontend_headers = fetch(base_url, "", context)
    assert health_status == ready_status == frontend_status == 200
    assert json.loads(health_body)["status"] == "ok"
    assert json.loads(ready_body)["status"] == "ready"
    assert b'<div id="root">' in frontend_body
    assert health_headers.get("Strict-Transport-Security") == "max-age=31536000"
    assert "default-src 'self'" in frontend_headers.get("Content-Security-Policy", "")
    assert_http_redirect(base_url, context)
    print("Production HTTPS smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
