"""Bounded acquisition of files from registered repository providers."""

from __future__ import annotations

import base64
import binascii
import json
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx2
from anyio import fail_after, to_thread

from arduino_component_kb.imports.domain import SourcePolicyError
from arduino_component_kb.imports.repository_domain import (
    RepositorySnapshot,
    normalize_repository_path,
    normalize_repository_url,
    require_commit_sha,
)
from arduino_component_kb.imports.urls import ApprovedUrl, pinned_url, require_public_address

_PROVIDER_HOSTS = frozenset({"api.github.com", "gitlab.com"})


class RepositoryAcquisitionError(Exception):
    """A safe, typed repository acquisition failure."""

    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


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
            raise RepositoryAcquisitionError("repository_dns_failed", retryable=True) from error
        if not addresses:
            raise RepositoryAcquisitionError("repository_dns_empty", retryable=True)
        return addresses


@dataclass(frozen=True, slots=True)
class AcquisitionPolicy:
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 20.0
    total_timeout_seconds: float = 30.0
    max_response_bytes: int = 8 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AcquiredEntry:
    snapshot: RepositorySnapshot
    file_path: str
    bytes_downloaded: int


@dataclass(frozen=True, slots=True)
class DiscoveredRepositoryFile:
    file_path: str
    size: int | None


@dataclass(frozen=True, slots=True)
class RepositoryDiscoveryResult:
    repository_url: str
    revision: str
    files: tuple[DiscoveredRepositoryFile, ...]
    files_scanned: int


_DISCOVERY_TOKEN = re.compile(r"[^a-z0-9]+")


class RepositoryAcquirer:
    """Resolve and read one file without cloning or extracting a repository."""

    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        policy: AcquisitionPolicy | None = None,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self.resolver = resolver or SystemHostResolver()
        self.policy = policy or AcquisitionPolicy()
        self.transport = transport

    async def acquire(
        self,
        source_key: str,
        repository_url: str,
        requested_revision: str,
        file_path: str,
    ) -> AcquiredEntry:
        repository = normalize_repository_url(repository_url)
        safe_path = normalize_repository_path(file_path)
        provider = self._provider(source_key, repository)
        timeout = httpx2.Timeout(
            self.policy.read_timeout_seconds,
            connect=self.policy.connect_timeout_seconds,
            read=self.policy.read_timeout_seconds,
            write=self.policy.read_timeout_seconds,
            pool=self.policy.connect_timeout_seconds,
        )
        try:
            with fail_after(self.policy.total_timeout_seconds):
                async with httpx2.AsyncClient(
                    transport=self.transport
                    or httpx2.AsyncHTTPTransport(
                        verify=ssl.create_default_context(), trust_env=False, retries=0
                    ),
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    proxy=None,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "User-Agent": "ArduinoComponentKBRepositoryImporter/1.0",
                    },
                ) as client:
                    revision = await self._resolve(client, provider, requested_revision)
                    content = await self._file(client, provider, revision, safe_path)
        except TimeoutError as error:
            raise RepositoryAcquisitionError("repository_total_timeout", retryable=True) from error
        except httpx2.TimeoutException as error:
            raise RepositoryAcquisitionError("repository_http_timeout", retryable=True) from error
        except httpx2.TransportError as error:
            raise RepositoryAcquisitionError(
                "repository_transport_failed", retryable=True
            ) from error
        snapshot = RepositorySnapshot(repository, revision, {safe_path: content})
        return AcquiredEntry(snapshot, safe_path, len(content))

    async def discover_files(
        self,
        source_key: str,
        repository_url: str,
        requested_revision: str,
        *,
        query: str | None = None,
        limit: int = 100,
    ) -> RepositoryDiscoveryResult:
        """List a bounded set of supported files at one immutable revision."""
        repository = normalize_repository_url(repository_url)
        provider = self._provider(source_key, repository)
        bounded_limit = min(max(limit, 1), 100)
        timeout = httpx2.Timeout(
            self.policy.read_timeout_seconds,
            connect=self.policy.connect_timeout_seconds,
            read=self.policy.read_timeout_seconds,
            write=self.policy.read_timeout_seconds,
            pool=self.policy.connect_timeout_seconds,
        )
        try:
            with fail_after(self.policy.total_timeout_seconds):
                async with httpx2.AsyncClient(
                    transport=self.transport
                    or httpx2.AsyncHTTPTransport(
                        verify=ssl.create_default_context(), trust_env=False, retries=0
                    ),
                    timeout=timeout,
                    follow_redirects=False,
                    trust_env=False,
                    proxy=None,
                    headers={
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                        "User-Agent": "ArduinoComponentKBRepositoryImporter/1.0",
                    },
                ) as client:
                    revision = await self._resolve(client, provider, requested_revision)
                    if provider == "github":
                        candidates, scanned = await self._github_files(client, revision)
                    else:
                        candidates, scanned = await self._gitlab_files(client, revision)
        except TimeoutError as error:
            raise RepositoryAcquisitionError("repository_total_timeout", retryable=True) from error
        except httpx2.TimeoutException as error:
            raise RepositoryAcquisitionError("repository_http_timeout", retryable=True) from error
        except httpx2.TransportError as error:
            raise RepositoryAcquisitionError(
                "repository_transport_failed", retryable=True
            ) from error
        needle = self._search_text(query or "")
        filtered = tuple(
            candidate
            for candidate in candidates
            if not needle or needle in self._search_text(candidate.file_path)
        )[:bounded_limit]
        return RepositoryDiscoveryResult(repository, revision, filtered, scanned)

    @staticmethod
    def _provider(source_key: str, repository_url: str) -> str:
        expected = {
            "seeed_wiki": "https://github.com/Seeed-Studio/wiki-documents",
            "kicad_symbols": "https://gitlab.com/kicad/libraries/kicad-symbols",
        }
        if source_key not in expected or repository_url != expected[source_key]:
            raise RepositoryAcquisitionError("repository_not_allowlisted")
        return "github" if source_key == "seeed_wiki" else "gitlab"

    async def _resolve(
        self, client: httpx2.AsyncClient, provider: str, requested_revision: str
    ) -> str:
        requested = requested_revision.strip()
        if not requested or len(requested) > 100 or any(ord(char) < 33 for char in requested):
            raise RepositoryAcquisitionError("repository_revision_invalid")
        encoded = quote(requested, safe="")
        if provider == "github":
            url = "https://api.github.com/repos/Seeed-Studio/wiki-documents/commits/" + encoded
            key = "sha"
        else:
            project = quote("kicad/libraries/kicad-symbols", safe="")
            url = f"https://gitlab.com/api/v4/projects/{project}/repository/commits/{encoded}"
            key = "id"
        payload = await self._json_dict(client, url)
        revision = payload.get(key)
        if not isinstance(revision, str):
            raise RepositoryAcquisitionError("repository_revision_response_invalid")
        try:
            return require_commit_sha(revision)
        except ValueError as error:
            raise RepositoryAcquisitionError("repository_revision_response_invalid") from error

    async def _file(
        self, client: httpx2.AsyncClient, provider: str, revision: str, file_path: str
    ) -> bytes:
        encoded_path = quote(file_path, safe="")
        if provider == "github":
            url = (
                "https://api.github.com/repos/Seeed-Studio/wiki-documents/contents/"
                f"{encoded_path}?ref={revision}"
            )
        else:
            project = quote("kicad/libraries/kicad-symbols", safe="")
            url = (
                f"https://gitlab.com/api/v4/projects/{project}/repository/files/"
                f"{encoded_path}?ref={revision}"
            )
        payload = await self._json_dict(client, url)
        if provider == "github" and payload.get("type") != "file":
            raise RepositoryAcquisitionError("repository_entry_not_regular_file")
        encoded_content = payload.get("content")
        if payload.get("encoding") != "base64" or not isinstance(encoded_content, str):
            raise RepositoryAcquisitionError("repository_file_response_invalid")
        compact_content = "".join(encoded_content.split())
        try:
            content = base64.b64decode(compact_content, validate=True)
        except (binascii.Error, ValueError) as error:
            raise RepositoryAcquisitionError("repository_file_encoding_invalid") from error
        if len(content) > self.policy.max_file_bytes:
            raise RepositoryAcquisitionError("repository_file_too_large")
        return content

    async def _github_files(
        self, client: httpx2.AsyncClient, revision: str
    ) -> tuple[tuple[DiscoveredRepositoryFile, ...], int]:
        treeish = revision
        for segment in ("sites", "en", "docs"):
            tree = await self._github_tree(client, treeish, recursive=False)
            subtree_sha: str | None = None
            for value in tree:
                if (
                    isinstance(value, dict)
                    and value.get("path") == segment
                    and value.get("type") == "tree"
                    and isinstance(value.get("sha"), str)
                ):
                    subtree_sha = value["sha"]
                    break
            if subtree_sha is None:
                raise RepositoryAcquisitionError("repository_discovery_root_missing")
            treeish = subtree_sha
        tree = await self._github_tree(client, treeish, recursive=True)
        return self._supported_files(tree, "github", prefix="sites/en/docs/")

    async def _github_tree(
        self, client: httpx2.AsyncClient, treeish: str, *, recursive: bool
    ) -> list[object]:
        suffix = "?recursive=1" if recursive else ""
        url = (
            "https://api.github.com/repos/Seeed-Studio/wiki-documents/git/trees/"
            f"{quote(treeish, safe='')}{suffix}"
        )
        payload = await self._json_dict(client, url)
        if payload.get("truncated") is True:
            raise RepositoryAcquisitionError("repository_discovery_truncated")
        tree = payload.get("tree")
        if not isinstance(tree, list):
            raise RepositoryAcquisitionError("repository_discovery_response_invalid")
        return tree

    async def _gitlab_files(
        self, client: httpx2.AsyncClient, revision: str
    ) -> tuple[tuple[DiscoveredRepositoryFile, ...], int]:
        project = quote("kicad/libraries/kicad-symbols", safe="")
        collected: list[object] = []
        # Supported KiCad 9.x libraries are root-level `.kicad_sym` files.  Do not
        # recursively enumerate the repository: it is both unnecessary for this
        # adapter contract and too broad for an interactive discovery request.
        for page in range(1, 11):
            url = (
                f"https://gitlab.com/api/v4/projects/{project}/repository/tree"
                f"?ref={revision}&per_page=100&page={page}"
            )
            values = await self._json_list(client, url)
            collected.extend(values)
            if len(values) < 100:
                return self._supported_files(collected, "gitlab")
        raise RepositoryAcquisitionError("repository_discovery_truncated")

    @staticmethod
    def _supported_files(
        values: list[object], provider: str, *, prefix: str = ""
    ) -> tuple[tuple[DiscoveredRepositoryFile, ...], int]:
        if len(values) > 10_000:
            raise RepositoryAcquisitionError("repository_file_count_exceeded")
        discovered: list[DiscoveredRepositoryFile] = []
        for value in values:
            if not isinstance(value, dict):
                continue
            kind = value.get("type")
            if kind != "blob":
                continue
            path = value.get("path")
            if not isinstance(path, str):
                continue
            try:
                safe_path = normalize_repository_path(prefix + path)
            except ValueError:
                continue
            suffix = safe_path.casefold()
            if provider == "github":
                if not suffix.endswith((".md", ".mdx")):
                    continue
            elif not suffix.endswith(".kicad_sym"):
                continue
            raw_size = value.get("size")
            size = raw_size if isinstance(raw_size, int) and raw_size >= 0 else None
            discovered.append(DiscoveredRepositoryFile(safe_path, size))
        return tuple(sorted(discovered, key=lambda item: item.file_path)), len(values)

    @staticmethod
    def _search_text(value: str) -> str:
        return _DISCOVERY_TOKEN.sub(" ", value.casefold()).strip()

    async def _json_dict(self, client: httpx2.AsyncClient, url: str) -> dict[str, object]:
        value = await self._json_value(client, url)
        if not isinstance(value, dict):
            raise RepositoryAcquisitionError("repository_json_invalid")
        return value

    async def _json_list(self, client: httpx2.AsyncClient, url: str) -> list[object]:
        value = await self._json_value(client, url)
        if not isinstance(value, list):
            raise RepositoryAcquisitionError("repository_json_invalid")
        return value

    async def _json_value(self, client: httpx2.AsyncClient, url: str) -> object:
        response = await self._request(client, url)
        try:
            if response.status_code == 404:
                raise RepositoryAcquisitionError("repository_entry_not_found")
            rate_limited = (
                response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"
            )
            if response.status_code == 429 or response.status_code >= 500 or rate_limited:
                raise RepositoryAcquisitionError("repository_provider_unavailable", retryable=True)
            if response.status_code != 200:
                raise RepositoryAcquisitionError("repository_provider_rejected")
            media_type = response.headers.get("content-type", "").partition(";")[0].strip()
            if media_type not in {"application/json", "application/vnd.github+json"}:
                raise RepositoryAcquisitionError("repository_content_type_invalid")
            body = await self._bounded_body(response)
            value = json.loads(body)
        except json.JSONDecodeError as error:
            raise RepositoryAcquisitionError("repository_json_invalid") from error
        finally:
            if not response.is_closed:
                await response.aclose()
        return value

    async def _request(self, client: httpx2.AsyncClient, url: str) -> httpx2.Response:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").casefold()
        if (
            parsed.scheme != "https"
            or host not in _PROVIDER_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in {None, 443}
        ):
            raise RepositoryAcquisitionError("repository_provider_url_invalid")
        try:
            addresses = tuple(
                require_public_address(address) for address in await self.resolver.resolve(host)
            )
        except SourcePolicyError as error:
            raise RepositoryAcquisitionError("repository_dns_address_invalid") from error
        if not addresses:
            raise RepositoryAcquisitionError("repository_dns_empty", retryable=True)
        target = sorted(addresses, key=lambda value: (value.version, int(value)))[0]
        path_and_query = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        approved = ApprovedUrl(url, host, path_and_query)
        request = client.build_request(
            "GET",
            pinned_url(approved, target),
            headers={"Host": host},
            extensions={"sni_hostname": host},
        )
        return await client.send(request, stream=True, follow_redirects=False)

    async def _bounded_body(self, response: httpx2.Response) -> bytes:
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in response.aiter_bytes():
                total += len(chunk)
                if total > self.policy.max_response_bytes:
                    raise RepositoryAcquisitionError("repository_response_too_large")
                chunks.append(chunk)
        finally:
            await response.aclose()
        return b"".join(chunks)
