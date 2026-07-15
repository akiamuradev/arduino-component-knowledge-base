"""SSRF-resistant HTTPX transport with DNS validation and connection pinning."""

from __future__ import annotations

import re
import socket
import ssl
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin

import httpx2
from anyio import fail_after, to_thread

from arduino_component_kb.imports.domain import SourceFetchError, SourcePolicyError
from arduino_component_kb.imports.urls import (
    ApprovedUrl,
    approve_source_url,
    pinned_url,
    require_public_address,
)

_CHARSET = re.compile(r"charset\s*=\s*['\"]?([A-Za-z0-9._-]+)", re.IGNORECASE)
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ALLOWED_ENCODINGS = frozenset({"utf-8", "utf8", "windows-1251", "cp1251"})


class HostResolver(Protocol):
    async def resolve(self, host: str) -> tuple[str, ...]: ...


class SystemHostResolver:
    async def resolve(self, host: str) -> tuple[str, ...]:
        def lookup() -> tuple[str, ...]:
            records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            return tuple(sorted({str(record[4][0]) for record in records}))

        try:
            addresses = await to_thread.run_sync(lookup)
        except OSError as error:
            raise SourceFetchError("source_dns_failed") from error
        if not addresses:
            raise SourceFetchError("source_dns_empty")
        return addresses


@dataclass(frozen=True, slots=True)
class ParserHttpPolicy:
    connect_timeout_seconds: float = 3.0
    read_timeout_seconds: float = 5.0
    total_timeout_seconds: float = 10.0
    max_redirects: int = 3
    max_header_bytes: int = 32 * 1024
    max_body_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    requested_url: str
    final_url: str
    content_type: str
    body: bytes

    def text(self) -> str:
        match = _CHARSET.search(self.content_type)
        encoding = match.group(1).lower() if match else "utf-8"
        if encoding not in _ALLOWED_ENCODINGS:
            raise SourcePolicyError("source_charset_not_allowed")
        try:
            return self.body.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError) as error:
            raise SourcePolicyError("source_body_encoding_invalid") from error


class SafeHttpFetcher:
    """Fetch allowlisted HTML without trusting DNS for the connection target."""

    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        policy: ParserHttpPolicy | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.resolver = resolver or SystemHostResolver()
        self.policy = policy or ParserHttpPolicy()
        self.transport = transport

    async def fetch(self, url: str) -> FetchedDocument:
        requested = approve_source_url(url)
        current = requested
        timeout = httpx2.Timeout(
            self.policy.read_timeout_seconds,
            connect=self.policy.connect_timeout_seconds,
            read=self.policy.read_timeout_seconds,
            write=self.policy.read_timeout_seconds,
            pool=self.policy.connect_timeout_seconds,
        )
        ssl_context = ssl.create_default_context()
        try:
            with fail_after(self.policy.total_timeout_seconds):
                async with httpx2.AsyncClient(
                    transport=self.transport
                    or httpx2.AsyncHTTPTransport(
                        verify=ssl_context,
                        trust_env=False,
                        retries=0,
                    ),
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    proxy=None,
                    headers={
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Encoding": "identity",
                        "User-Agent": "ArduinoComponentKBParser/0.7",
                    },
                ) as client:
                    for redirect_count in range(self.policy.max_redirects + 1):
                        response = await self._request(client, current)
                        if response.status_code in _REDIRECT_STATUSES:
                            location = response.headers.get("location")
                            await response.aclose()
                            if location is None or redirect_count >= self.policy.max_redirects:
                                raise SourcePolicyError("source_redirect_limit_exceeded")
                            current = approve_source_url(urljoin(current.url, location))
                            continue
                        if response.status_code != 200:
                            await response.aclose()
                            raise SourceFetchError("source_http_status_failed")
                        content_type = response.headers.get("content-type", "")
                        media_type = content_type.partition(";")[0].strip().lower()
                        if media_type not in {"text/html", "application/xhtml+xml"}:
                            await response.aclose()
                            raise SourcePolicyError("source_content_type_not_allowed")
                        body = await self._bounded_body(response)
                        return FetchedDocument(requested.url, current.url, content_type, body)
        except TimeoutError as error:
            raise SourceFetchError("source_total_timeout") from error
        except httpx2.TimeoutException as error:
            raise SourceFetchError("source_http_timeout") from error
        except httpx2.TransportError as error:
            raise SourceFetchError("source_transport_failed") from error
        raise SourceFetchError("source_redirect_state_invalid")

    async def _request(self, client: httpx2.AsyncClient, approved: ApprovedUrl) -> httpx2.Response:
        raw_addresses = await self.resolver.resolve(approved.host)
        addresses = tuple(require_public_address(value) for value in raw_addresses)
        if not addresses:
            raise SourceFetchError("source_dns_empty")
        target = sorted(addresses, key=lambda value: (value.version, int(value)))[0]
        client.cookies.clear()
        request = client.build_request(
            "GET",
            pinned_url(approved, target),
            headers={"Host": approved.host},
            extensions={"sni_hostname": approved.host},
        )
        response = await client.send(request, stream=True, follow_redirects=False)
        header_bytes = sum(
            len(name.encode("latin-1")) + len(value.encode("latin-1")) + 4
            for name, value in response.headers.multi_items()
        )
        if header_bytes > self.policy.max_header_bytes:
            await response.aclose()
            raise SourcePolicyError("source_headers_too_large")
        return response

    async def _bounded_body(self, response: httpx2.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self.policy.max_body_bytes:
                    raise SourcePolicyError("source_body_too_large")
                chunks.append(chunk)
        finally:
            await response.aclose()
        return b"".join(chunks)
