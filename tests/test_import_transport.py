"""Adversarial tests for redirect, DNS pinning, MIME, cookie, and body limits."""

from __future__ import annotations

import gzip
from collections.abc import Callable

import httpx2
import pytest

from arduino_component_kb.imports.domain import SourcePolicyError
from arduino_component_kb.imports.transport import ParserHttpPolicy, SafeHttpFetcher


class StaticResolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses
        self.hosts: list[str] = []

    async def resolve(self, host: str) -> tuple[str, ...]:
        self.hosts.append(host)
        return self.addresses


def transport(handler: Callable[[httpx2.Request], httpx2.Response]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


async def test_fetch_pins_public_ip_preserves_host_and_drops_redirect_cookie() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "arduino-tex.ru"
        assert request.extensions["sni_hostname"] == "arduino-tex.ru"
        if request.url.path == "/start":
            return httpx2.Response(
                302,
                headers={"Location": "/final", "Set-Cookie": "remote=value"},
            )
        assert "cookie" not in request.headers
        return httpx2.Response(
            200,
            headers={"Content-Type": "text/html; charset=utf-8"},
            content=b"<html><h1>safe</h1></html>",
        )

    resolver = StaticResolver("93.184.216.34")
    document = await SafeHttpFetcher(
        resolver=resolver,
        transport=transport(handler),
    ).fetch("https://arduino-tex.ru/start")

    assert document.final_url == "https://arduino-tex.ru/final"
    assert document.text() == "<html><h1>safe</h1></html>"
    assert resolver.hosts == ["arduino-tex.ru", "arduino-tex.ru"]
    assert len(seen) == 2


async def test_any_private_dns_answer_blocks_connection() -> None:
    called = False

    def handler(_: httpx2.Request) -> httpx2.Response:
        nonlocal called
        called = True
        return httpx2.Response(200)

    fetcher = SafeHttpFetcher(
        resolver=StaticResolver("93.184.216.34", "127.0.0.1"),
        transport=transport(handler),
    )
    with pytest.raises(SourcePolicyError, match="source_dns_address_forbidden"):
        await fetcher.fetch("https://arduino-tex.ru/news/1/item.html")
    assert called is False


async def test_redirect_to_non_allowlisted_host_is_rejected() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(302, headers={"Location": "https://evil.invalid/private"})

    fetcher = SafeHttpFetcher(
        resolver=StaticResolver("93.184.216.34"),
        transport=transport(handler),
    )
    with pytest.raises(SourcePolicyError, match="source_host_not_allowed"):
        await fetcher.fetch("https://arduino-tex.ru/news/1/item.html")


async def test_decoded_body_limit_is_enforced() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"x" * 17,
        )

    fetcher = SafeHttpFetcher(
        resolver=StaticResolver("93.184.216.34"),
        policy=ParserHttpPolicy(max_body_bytes=16),
        transport=transport(handler),
    )
    with pytest.raises(SourcePolicyError, match="source_body_too_large"):
        await fetcher.fetch("https://arduino-tex.ru/news/1/item.html")


async def test_non_html_response_is_rejected() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "application/octet-stream"},
            content=b"not html",
        )

    fetcher = SafeHttpFetcher(
        resolver=StaticResolver("93.184.216.34"),
        transport=transport(handler),
    )
    with pytest.raises(SourcePolicyError, match="source_content_type_not_allowed"):
        await fetcher.fetch("https://arduino-tex.ru/news/1/item.html")


async def test_decoded_compressed_body_cannot_bypass_limit() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "text/html", "Content-Encoding": "gzip"},
            content=gzip.compress(b"x" * 64),
        )

    fetcher = SafeHttpFetcher(
        resolver=StaticResolver("93.184.216.34"),
        policy=ParserHttpPolicy(max_body_bytes=32),
        transport=transport(handler),
    )
    with pytest.raises(SourcePolicyError, match="source_body_too_large"):
        await fetcher.fetch("https://arduino-tex.ru/news/1/item.html")


async def test_response_header_limit_is_enforced_before_body_read() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            headers={"Content-Type": "text/html", "X-Oversized": "x" * 64},
            content=b"safe",
        )

    fetcher = SafeHttpFetcher(
        resolver=StaticResolver("93.184.216.34"),
        policy=ParserHttpPolicy(max_header_bytes=32),
        transport=transport(handler),
    )
    with pytest.raises(SourcePolicyError, match="source_headers_too_large"):
        await fetcher.fetch("https://arduino-tex.ru/news/1/item.html")
