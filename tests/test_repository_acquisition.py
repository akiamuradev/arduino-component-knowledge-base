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
                "content": base64.b64encode(content).decode() + "\n",
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


async def test_github_rate_limit_is_a_retryable_provider_failure() -> None:
    def handler(_: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            403,
            headers={
                "Content-Type": "application/json",
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": "1784501637",
            },
            content=b'{"message":"API rate limit exceeded"}',
        )

    with pytest.raises(RepositoryAcquisitionError) as raised:
        await RepositoryAcquirer(
            resolver=StaticResolver("93.184.216.34"), transport=transport(handler)
        ).acquire(
            "seeed_wiki",
            "https://github.com/Seeed-Studio/wiki-documents",
            "main",
            "README.md",
        )
    assert raised.value.code == "repository_provider_unavailable"
    assert raised.value.retryable is True


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


async def test_github_discovery_is_bounded_and_normalizes_query() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "/commits/" in request.url.path:
            return response({"sha": "d" * 40})
        treeish = request.url.path.rsplit("/", 1)[-1]
        if treeish == "d" * 40:
            return response(
                {"truncated": False, "tree": [{"path": "sites", "type": "tree", "sha": "1" * 40}]}
            )
        if treeish == "1" * 40:
            return response(
                {"truncated": False, "tree": [{"path": "en", "type": "tree", "sha": "2" * 40}]}
            )
        if treeish == "2" * 40:
            return response(
                {"truncated": False, "tree": [{"path": "docs", "type": "tree", "sha": "3" * 40}]}
            )
        return response(
            {
                "truncated": False,
                "tree": [
                    {
                        "path": "Sensor/Grove-Button.md",
                        "type": "blob",
                        "size": 1234,
                    },
                    {
                        "path": "Sensor/Grove-Relay.mdx",
                        "type": "blob",
                        "size": 2345,
                    },
                    {"path": "Sensor/button.png", "type": "blob", "size": 99},
                    {"path": "Sensor", "type": "tree"},
                ],
            }
        )

    result = await RepositoryAcquirer(
        resolver=StaticResolver("93.184.216.34"), transport=transport(handler)
    ).discover_files(
        "seeed_wiki",
        "https://github.com/Seeed-Studio/wiki-documents",
        "main",
        query="Grove Button",
        limit=1,
    )
    assert result.revision == "d" * 40
    assert result.files_scanned == 4
    assert [item.file_path for item in result.files] == ["sites/en/docs/Sensor/Grove-Button.md"]
    assert result.files[0].size == 1234


async def test_github_truncated_tree_is_rejected() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "/commits/" in request.url.path:
            return response({"sha": "e" * 40})
        treeish = request.url.path.rsplit("/", 1)[-1]
        if treeish == "e" * 40:
            return response(
                {"truncated": False, "tree": [{"path": "sites", "type": "tree", "sha": "1" * 40}]}
            )
        if treeish == "1" * 40:
            return response(
                {"truncated": False, "tree": [{"path": "en", "type": "tree", "sha": "2" * 40}]}
            )
        if treeish == "2" * 40:
            return response(
                {"truncated": False, "tree": [{"path": "docs", "type": "tree", "sha": "3" * 40}]}
            )
        return response({"truncated": True, "tree": []})

    with pytest.raises(RepositoryAcquisitionError, match="repository_discovery_truncated"):
        await RepositoryAcquirer(
            resolver=StaticResolver("93.184.216.34"), transport=transport(handler)
        ).discover_files(
            "seeed_wiki",
            "https://github.com/Seeed-Studio/wiki-documents",
            "main",
        )


async def test_gitlab_discovery_returns_only_symbol_files() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if "/commits/" in request.url.path:
            return response({"id": "f" * 40})
        assert "recursive" not in request.url.params
        assert request.url.params["page"] == "1"
        return httpx2.Response(
            200,
            headers={"Content-Type": "application/json"},
            content=json.dumps(
                [
                    {"path": "Sensor_Temperature.kicad_sym", "type": "blob"},
                    {"path": "README.md", "type": "blob"},
                    {"path": "symbols", "type": "tree"},
                ]
            ).encode(),
        )

    result = await RepositoryAcquirer(
        resolver=StaticResolver("93.184.216.34"), transport=transport(handler)
    ).discover_files(
        "kicad_symbols",
        "https://gitlab.com/kicad/libraries/kicad-symbols",
        "master",
        query="sensor temperature",
    )
    assert result.revision == "f" * 40
    assert result.files_scanned == 3
    assert [item.file_path for item in result.files] == ["Sensor_Temperature.kicad_sym"]
