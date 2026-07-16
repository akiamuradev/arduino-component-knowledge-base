"""Network-policy tests for registered repository acquisition."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx2
import pytest

from arduino_component_kb.imports.acquisition import (
    AcquisitionPolicy,
    RepositoryAcquirer,
    RepositoryAcquisitionError,
)


class StaticResolver:
    def __init__(self, *addresses: str) -> None:
        self.addresses = addresses
        self.hosts: list[str] = []

    async def resolve(self, host: str) -> tuple[str, ...]:
        self.hosts.append(host)
        return self.addresses


def transport(handler: Callable[[httpx2.Request], httpx2.Response]) -> httpx2.MockTransport:
    return httpx2.MockTransport(handler)


def response(payload: dict[str, object]) -> httpx2.Response:
    return httpx2.Response(
        200,
        headers={"Content-Type": "application/json"},
        content=json.dumps(payload).encode(),
    )


async def test_github_revision_and_file_are_pinned_and_bounded() -> None:
    content = b"# Grove Button\n"
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "api.github.com"
        assert request.extensions["sni_hostname"] == "api.github.com"
        seen.append(request.url.path)
        if "/commits/" in request.url.path:
            return response({"sha": "a" * 40})
        return response(
            {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(content).decode(),
            }
        )

    resolver = StaticResolver("93.184.216.34")
    result = await RepositoryAcquirer(resolver=resolver, transport=transport(handler)).acquire(
        "seeed_wiki",
        "https://github.com/Seeed-Studio/wiki-documents",
        "main",
        "docs/Sensor/Grove_Button.md",
    )

    assert result.snapshot.revision == "a" * 40
    assert result.snapshot.read("docs/Sensor/Grove_Button.md") == content
    assert result.bytes_downloaded == len(content)
    assert len(seen) == 2
    assert resolver.hosts == ["api.github.com", "api.github.com"]


async def test_gitlab_uses_registered_project_and_full_sha() -> None:
    content = b"(kicad_symbol_lib (version 20231120))"

    def handler(request: httpx2.Request) -> httpx2.Response:
        assert request.headers["host"] == "gitlab.com"
        if "/commits/" in request.url.path:
            return response({"id": "b" * 40})
        return response({"encoding": "base64", "content": base64.b64encode(content).decode()})

    result = await RepositoryAcquirer(
        resolver=StaticResolver("93.184.216.34"), transport=transport(handler)
    ).acquire(
        "kicad_symbols",
        "https://gitlab.com/kicad/libraries/kicad-symbols",
        "master",
        "Sensor_Temperature.kicad_sym",
    )
    assert result.snapshot.revision == "b" * 40
    assert result.snapshot.read("Sensor_Temperature.kicad_sym") == content


@pytest.mark.parametrize(
    ("source", "repository", "code"),
    [
        ("unknown", "https://github.com/Seeed-Studio/wiki-documents", "not_allowlisted"),
        ("seeed_wiki", "https://github.com/attacker/repository", "not_allowlisted"),
    ],
)
async def test_arbitrary_repository_is_rejected_before_network(
    source: str, repository: str, code: str
) -> None:
    with pytest.raises(RepositoryAcquisitionError, match=code):
        await RepositoryAcquirer(resolver=StaticResolver("93.184.216.34")).acquire(
            source, repository, "main", "README.md"
        )


async def test_private_provider_dns_answer_is_rejected() -> None:
    with pytest.raises(RepositoryAcquisitionError, match="repository_dns_address_invalid"):
        await RepositoryAcquirer(resolver=StaticResolver("127.0.0.1")).acquire(
            "seeed_wiki",
            "https://github.com/Seeed-Studio/wiki-documents",
            "main",
            "README.md",
        )


async def test_oversized_file_is_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "/commits/" in request.url.path:
            return response({"sha": "c" * 40})
        return response(
            {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(b"x" * 17).decode(),
            }
        )

    acquirer = RepositoryAcquirer(
        resolver=StaticResolver("93.184.216.34"),
        policy=AcquisitionPolicy(max_file_bytes=16),
        transport=transport(handler),
    )
    with pytest.raises(RepositoryAcquisitionError, match="repository_file_too_large"):
        await acquirer.acquire(
            "seeed_wiki",
            "https://github.com/Seeed-Studio/wiki-documents",
            "main",
            "README.md",
        )


async def test_path_traversal_is_rejected_before_network() -> None:
    with pytest.raises(ValueError, match="repository_path_outside_snapshot"):
        await RepositoryAcquirer(resolver=StaticResolver("93.184.216.34")).acquire(
            "seeed_wiki",
            "https://github.com/Seeed-Studio/wiki-documents",
            "main",
            "../secret",
        )
