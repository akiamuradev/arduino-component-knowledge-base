"""Immutable, verified KiCad index artifacts for online shadow workers."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath

from arduino_component_kb.imports.pipeline.enrichment.kicad_index import (
    DEFAULT_KICAD_LIBRARY_ALLOWLIST,
    KICAD_REPOSITORY_URL,
    KicadIndexBuildStats,
    KicadIndexSnapshot,
    KicadSymbolIndexer,
)
from arduino_component_kb.imports.pipeline.models import KicadSymbolIndex, KicadSymbolRecord
from arduino_component_kb.imports.repository_domain import (
    normalize_repository_path,
    normalize_repository_url,
    require_commit_sha,
)

KICAD_INDEX_ARTIFACT_SCHEMA = "kicad-index-artifact/v1"
MAX_KICAD_INDEX_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_KICAD_INDEX_LIBRARY_BYTES = 16 * 1024 * 1024
MAX_KICAD_INDEX_SNAPSHOT_BYTES = 256 * 1024 * 1024
MAX_KICAD_INDEX_LIBRARIES = 2_000
MAX_KICAD_INDEX_SYMBOLS = 250_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "repository_url",
        "source_revision",
        "parser_version",
        "index_sha256",
        "symbol_count",
        "libraries",
    }
)
_LIBRARY_KEYS = frozenset({"source_path", "content_sha256", "symbol_count"})
_RECORD_KEYS = frozenset(
    {
        "library",
        "symbol_name",
        "aliases",
        "normalized_names",
        "description",
        "keywords",
        "manufacturer_hints",
        "datasheet",
        "pins",
        "footprint_filters",
        "source_path",
        "source_revision",
        "source_content_sha256",
        "parser_version",
        "is_generic",
    }
)
_PIN_KEYS = frozenset({"number", "name", "electrical_type", "unit"})


class KicadIndexArtifactError(ValueError):
    """Expose only a bounded machine-readable artifact failure code."""

    def __init__(self, code: str) -> None:
        if re.fullmatch(r"kicad_index_[a-z0-9_]{1,70}", code) is None:
            code = "kicad_index_artifact_invalid"
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class KicadIndexSourceSnapshot:
    """KiCad-only snapshot with limits independent from one-file card imports."""

    repository_url: str
    revision: str
    files: Mapping[str, bytes]

    def __post_init__(self) -> None:
        try:
            repository_url = normalize_repository_url(self.repository_url)
            revision = require_commit_sha(self.revision)
            normalized = {
                normalize_repository_path(path): content
                for path, content in self.files.items()
            }
        except ValueError as error:
            raise KicadIndexArtifactError("kicad_index_snapshot_invalid") from error
        if repository_url != KICAD_REPOSITORY_URL:
            raise KicadIndexArtifactError("kicad_index_repository_invalid")
        if not 1 <= len(normalized) <= MAX_KICAD_INDEX_LIBRARIES:
            raise KicadIndexArtifactError("kicad_index_snapshot_file_count_invalid")
        if any(
            not path.endswith(".kicad_sym")
            or not content
            or len(content) > MAX_KICAD_INDEX_LIBRARY_BYTES
            for path, content in normalized.items()
        ):
            raise KicadIndexArtifactError("kicad_index_snapshot_file_invalid")
        if sum(len(content) for content in normalized.values()) > MAX_KICAD_INDEX_SNAPSHOT_BYTES:
            raise KicadIndexArtifactError("kicad_index_snapshot_too_large")
        object.__setattr__(self, "repository_url", repository_url)
        object.__setattr__(self, "revision", revision)
        object.__setattr__(self, "files", normalized)


@dataclass(frozen=True, slots=True)
class KicadIndexLibraryManifest:
    source_path: str
    content_sha256: str
    symbol_count: int

    def __post_init__(self) -> None:
        try:
            normalized_path = normalize_repository_path(self.source_path)
        except ValueError as error:
            raise KicadIndexArtifactError("kicad_index_library_path_invalid") from error
        if not normalized_path.endswith(".kicad_sym"):
            raise KicadIndexArtifactError("kicad_index_library_path_invalid")
        if _SHA256.fullmatch(self.content_sha256) is None:
            raise KicadIndexArtifactError("kicad_index_library_digest_invalid")
        if not 0 <= self.symbol_count <= MAX_KICAD_INDEX_SYMBOLS:
            raise KicadIndexArtifactError("kicad_index_library_symbol_count_invalid")
        object.__setattr__(self, "source_path", normalized_path)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_path": self.source_path,
            "content_sha256": self.content_sha256,
            "symbol_count": self.symbol_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadIndexLibraryManifest:
        if frozenset(value) != _LIBRARY_KEYS:
            raise KicadIndexArtifactError("kicad_index_library_manifest_invalid")
        return cls(
            _required_string(value, "source_path"),
            _required_string(value, "content_sha256"),
            _required_int(value, "symbol_count"),
        )


@dataclass(frozen=True, slots=True)
class KicadIndexManifest:
    repository_url: str
    source_revision: str
    parser_version: str
    index_sha256: str
    symbol_count: int
    libraries: tuple[KicadIndexLibraryManifest, ...]
    schema_version: str = KICAD_INDEX_ARTIFACT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != KICAD_INDEX_ARTIFACT_SCHEMA:
            raise KicadIndexArtifactError("kicad_index_schema_unsupported")
        try:
            repository_url = normalize_repository_url(self.repository_url)
            source_revision = require_commit_sha(self.source_revision)
        except ValueError as error:
            raise KicadIndexArtifactError("kicad_index_manifest_source_invalid") from error
        if repository_url != KICAD_REPOSITORY_URL:
            raise KicadIndexArtifactError("kicad_index_repository_invalid")
        if self.parser_version != KicadSymbolIndexer.parser_version:
            raise KicadIndexArtifactError("kicad_index_parser_version_invalid")
        if _SHA256.fullmatch(self.index_sha256) is None:
            raise KicadIndexArtifactError("kicad_index_digest_invalid")
        if not 1 <= self.symbol_count <= MAX_KICAD_INDEX_SYMBOLS:
            raise KicadIndexArtifactError("kicad_index_symbol_count_invalid")
        if not 1 <= len(self.libraries) <= MAX_KICAD_INDEX_LIBRARIES:
            raise KicadIndexArtifactError("kicad_index_library_count_invalid")
        paths = tuple(item.source_path for item in self.libraries)
        if len(set(paths)) != len(paths) or paths != tuple(sorted(paths)):
            raise KicadIndexArtifactError("kicad_index_libraries_not_canonical")
        if sum(item.symbol_count for item in self.libraries) != self.symbol_count:
            raise KicadIndexArtifactError("kicad_index_manifest_count_mismatch")
        object.__setattr__(self, "repository_url", repository_url)
        object.__setattr__(self, "source_revision", source_revision)

    @property
    def manifest_sha256(self) -> str:
        return sha256(_canonical_json(self.as_dict())).hexdigest()

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "repository_url": self.repository_url,
            "source_revision": self.source_revision,
            "parser_version": self.parser_version,
            "index_sha256": self.index_sha256,
            "symbol_count": self.symbol_count,
            "libraries": [item.as_dict() for item in self.libraries],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> KicadIndexManifest:
        if frozenset(value) != _MANIFEST_KEYS:
            raise KicadIndexArtifactError("kicad_index_manifest_invalid")
        libraries = _required_list(value, "libraries")
        return cls(
            repository_url=_required_string(value, "repository_url"),
            source_revision=_required_string(value, "source_revision"),
            parser_version=_required_string(value, "parser_version"),
            index_sha256=_required_string(value, "index_sha256"),
            symbol_count=_required_int(value, "symbol_count"),
            libraries=tuple(
                KicadIndexLibraryManifest.from_dict(_required_mapping(item))
                for item in libraries
            ),
            schema_version=_required_string(value, "schema_version"),
        )


@dataclass(frozen=True, slots=True)
class LoadedKicadIndexArtifact:
    manifest: KicadIndexManifest
    index: KicadSymbolIndex


@dataclass(frozen=True, slots=True)
class BuiltKicadIndexArtifact:
    content: bytes
    loaded: LoadedKicadIndexArtifact
    stats: KicadIndexBuildStats


@dataclass(frozen=True, slots=True)
class _CachedArtifact:
    signature: tuple[int, int, int, int, int]
    expected_revision: str
    expected_sha256: str
    allowlist: tuple[str, ...]
    loaded: LoadedKicadIndexArtifact


class KicadIndexArtifactLoader:
    """Validate once per immutable file identity and reuse the in-process index."""

    def __init__(self) -> None:
        self._cache: dict[Path, _CachedArtifact] = {}

    def load(
        self,
        path: Path,
        *,
        expected_revision: str,
        expected_sha256: str,
        library_allowlist: tuple[str, ...] = DEFAULT_KICAD_LIBRARY_ALLOWLIST,
    ) -> LoadedKicadIndexArtifact:
        safe_path = _absolute_artifact_path(path)
        revision = _expected_revision(expected_revision)
        digest = _expected_digest(expected_sha256)
        allowlist = _validate_allowlist(library_allowlist)
        signature = _file_signature(safe_path)
        cached = self._cache.get(safe_path)
        if (
            cached is not None
            and cached.signature == signature
            and cached.expected_revision == revision
            and cached.expected_sha256 == digest
            and cached.allowlist == allowlist
        ):
            return cached.loaded
        content, opened_signature = _read_bounded_regular_file(
            safe_path,
            MAX_KICAD_INDEX_ARTIFACT_BYTES,
        )
        loaded = deserialize_kicad_index_artifact(
            content,
            expected_revision=revision,
            expected_sha256=digest,
            library_allowlist=allowlist,
        )
        self._cache[safe_path] = _CachedArtifact(
            opened_signature,
            revision,
            digest,
            allowlist,
            loaded,
        )
        return loaded


def build_kicad_index_artifact(
    snapshot: KicadIndexSnapshot,
    *,
    library_allowlist: tuple[str, ...] = DEFAULT_KICAD_LIBRARY_ALLOWLIST,
) -> BuiltKicadIndexArtifact:
    """Build deterministic artifact bytes from one immutable KiCad snapshot."""
    indexer = KicadSymbolIndexer(_validate_allowlist(library_allowlist))
    result = indexer.build(snapshot)
    cache = indexer.cache
    if cache is None or not result.index.records:
        raise KicadIndexArtifactError("kicad_index_empty")
    libraries = tuple(
        KicadIndexLibraryManifest(
            item.source_path,
            item.content_sha256,
            len(item.records),
        )
        for item in cache.libraries
    )
    manifest = KicadIndexManifest(
        KICAD_REPOSITORY_URL,
        result.index.source_revision,
        indexer.parser_version,
        result.index.index_sha256,
        len(result.index.records),
        libraries,
    )
    loaded = LoadedKicadIndexArtifact(manifest, result.index)
    payload = {
        "manifest": manifest.as_dict(),
        "records": [item.as_dict() for item in result.index.records],
    }
    content = _canonical_json(payload) + b"\n"
    if len(content) > MAX_KICAD_INDEX_ARTIFACT_BYTES:
        raise KicadIndexArtifactError("kicad_index_artifact_too_large")
    return BuiltKicadIndexArtifact(content, loaded, result.stats)


def deserialize_kicad_index_artifact(
    content: bytes,
    *,
    expected_revision: str,
    expected_sha256: str,
    library_allowlist: tuple[str, ...] = DEFAULT_KICAD_LIBRARY_ALLOWLIST,
) -> LoadedKicadIndexArtifact:
    """Fail closed when an artifact or configured pin is inconsistent."""
    if not content or len(content) > MAX_KICAD_INDEX_ARTIFACT_BYTES:
        raise KicadIndexArtifactError("kicad_index_artifact_size_invalid")
    try:
        decoded: object = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise KicadIndexArtifactError("kicad_index_artifact_json_invalid") from error
    root = _required_mapping(decoded)
    if frozenset(root) != {"manifest", "records"}:
        raise KicadIndexArtifactError("kicad_index_artifact_shape_invalid")
    manifest = KicadIndexManifest.from_dict(_required_mapping(root["manifest"]))
    revision = _expected_revision(expected_revision)
    digest = _expected_digest(expected_sha256)
    if manifest.source_revision != revision:
        raise KicadIndexArtifactError("kicad_index_revision_mismatch")
    if manifest.index_sha256 != digest:
        raise KicadIndexArtifactError("kicad_index_digest_mismatch")
    allowlist = _validate_allowlist(library_allowlist)
    record_values = _required_list(root, "records")
    if len(record_values) != manifest.symbol_count:
        raise KicadIndexArtifactError("kicad_index_record_count_mismatch")
    records: list[KicadSymbolRecord] = []
    for value in record_values:
        mapping = _required_mapping(value)
        _validate_record_shape(mapping)
        try:
            record = KicadSymbolRecord.from_dict(mapping)
        except ValueError as error:
            raise KicadIndexArtifactError("kicad_index_record_invalid") from error
        if not _library_allowed(record.library, allowlist):
            raise KicadIndexArtifactError("kicad_index_library_not_allowed")
        records.append(record)
    if tuple(item.record_id for item in records) != tuple(
        sorted(item.record_id for item in records)
    ):
        raise KicadIndexArtifactError("kicad_index_records_not_canonical")
    try:
        index = KicadSymbolIndex(tuple(records), manifest.source_revision)
    except ValueError as error:
        raise KicadIndexArtifactError("kicad_index_records_invalid") from error
    if index.index_sha256 != manifest.index_sha256:
        raise KicadIndexArtifactError("kicad_index_payload_digest_mismatch")
    _validate_library_manifest(manifest, index.records)
    return LoadedKicadIndexArtifact(manifest, index)


def publish_kicad_index_artifact(path: Path, content: bytes) -> Path:
    """Atomically create one immutable artifact and never overwrite a version."""
    safe_path = _absolute_artifact_path(path)
    parent = safe_path.parent
    try:
        parent_stat = parent.stat()
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_output_parent_unavailable") from error
    if parent.is_symlink() or not stat.S_ISDIR(parent_stat.st_mode):
        raise KicadIndexArtifactError("kicad_index_output_parent_invalid")
    if not content or len(content) > MAX_KICAD_INDEX_ARTIFACT_BYTES:
        raise KicadIndexArtifactError("kicad_index_artifact_size_invalid")
    try:
        target_metadata = safe_path.lstat()
    except FileNotFoundError:
        target_metadata = None
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_output_unavailable") from error
    if target_metadata is not None:
        if stat.S_ISLNK(target_metadata.st_mode):
            raise KicadIndexArtifactError("kicad_index_artifact_symlink_forbidden")
        existing, _ = _read_bounded_regular_file(
            safe_path,
            MAX_KICAD_INDEX_ARTIFACT_BYTES,
        )
        if existing == content:
            return safe_path
        raise KicadIndexArtifactError("kicad_index_artifact_exists")
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{safe_path.name}.",
            suffix=".tmp",
            dir=parent,
        )
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_artifact_publish_failed") from error
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o644)
        try:
            os.link(temporary, safe_path, follow_symlinks=False)
        except FileExistsError:
            existing, _ = _read_bounded_regular_file(
                safe_path,
                MAX_KICAD_INDEX_ARTIFACT_BYTES,
            )
            if existing != content:
                raise KicadIndexArtifactError("kicad_index_artifact_exists") from None
        _fsync_directory(parent)
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_artifact_publish_failed") from error
    finally:
        temporary.unlink(missing_ok=True)
    return safe_path


def snapshot_from_directory(
    root: Path,
    revision: str,
    *,
    library_allowlist: tuple[str, ...] = DEFAULT_KICAD_LIBRARY_ALLOWLIST,
    max_files: int = 1_000,
) -> KicadIndexSourceSnapshot:
    """Read a bounded, non-symlink local KiCad snapshot for the builder CLI."""
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_snapshot_unavailable") from error
    if root.is_symlink() or not resolved_root.is_dir():
        raise KicadIndexArtifactError("kicad_index_snapshot_invalid")
    if not 1 <= max_files <= 1_000:
        raise KicadIndexArtifactError("kicad_index_file_limit_invalid")
    allowlist = _validate_allowlist(library_allowlist)
    files: dict[str, bytes] = {}
    for candidate in sorted(resolved_root.rglob("*.kicad_sym")):
        if candidate.is_symlink():
            raise KicadIndexArtifactError("kicad_index_snapshot_symlink_forbidden")
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(resolved_root):
            raise KicadIndexArtifactError("kicad_index_snapshot_path_invalid")
        relative = resolved.relative_to(resolved_root).as_posix()
        library = _library_name(relative)
        if not _library_allowed(library, allowlist):
            continue
        if len(files) >= max_files:
            raise KicadIndexArtifactError("kicad_index_file_limit_exceeded")
        content, _ = _read_bounded_regular_file(resolved, MAX_KICAD_INDEX_LIBRARY_BYTES)
        files[relative] = content
    if not files:
        raise KicadIndexArtifactError("kicad_index_snapshot_empty")
    try:
        return KicadIndexSourceSnapshot(KICAD_REPOSITORY_URL, revision, files)
    except (KicadIndexArtifactError, ValueError) as error:
        raise KicadIndexArtifactError("kicad_index_snapshot_invalid") from error


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Build one immutable, verified KiCad index artifact."
    )
    command.add_argument("--snapshot-root", type=Path, required=True)
    command.add_argument("--revision", required=True, help="Full immutable KiCad commit SHA")
    command.add_argument("--output", type=Path, required=True)
    command.add_argument(
        "--allowlist",
        default=",".join(DEFAULT_KICAD_LIBRARY_ALLOWLIST),
        help="Comma-separated KiCad library prefixes",
    )
    command.add_argument("--max-files", type=int, default=1_000)
    return command


def main() -> None:
    args = parser().parse_args()
    allowlist = tuple(item.strip() for item in args.allowlist.split(",") if item.strip())
    try:
        snapshot = snapshot_from_directory(
            args.snapshot_root,
            args.revision,
            library_allowlist=allowlist,
            max_files=args.max_files,
        )
        built = build_kicad_index_artifact(snapshot, library_allowlist=allowlist)
        output = publish_kicad_index_artifact(args.output, built.content)
    except KicadIndexArtifactError as error:
        raise SystemExit(error.code) from error
    print(
        json.dumps(
            {
                "schema_version": KICAD_INDEX_ARTIFACT_SCHEMA,
                "output": str(output),
                "repository_url": built.loaded.manifest.repository_url,
                "source_revision": built.loaded.manifest.source_revision,
                "parser_version": built.loaded.manifest.parser_version,
                "index_sha256": built.loaded.manifest.index_sha256,
                "manifest_sha256": built.loaded.manifest.manifest_sha256,
                "symbol_count": built.loaded.manifest.symbol_count,
                "library_count": len(built.loaded.manifest.libraries),
                "warnings": list(built.stats.warnings),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _validate_library_manifest(
    manifest: KicadIndexManifest,
    records: Sequence[KicadSymbolRecord],
) -> None:
    expected = {item.source_path: item for item in manifest.libraries}
    counts = {path: 0 for path in expected}
    for record in records:
        library = expected.get(record.source_path)
        if library is None:
            raise KicadIndexArtifactError("kicad_index_record_library_missing")
        if record.source_content_sha256 != library.content_sha256:
            raise KicadIndexArtifactError("kicad_index_library_digest_mismatch")
        if record.parser_version != manifest.parser_version:
            raise KicadIndexArtifactError("kicad_index_record_parser_mismatch")
        counts[record.source_path] += 1
    if any(counts[item.source_path] != item.symbol_count for item in manifest.libraries):
        raise KicadIndexArtifactError("kicad_index_library_count_mismatch")


def _validate_record_shape(value: Mapping[str, object]) -> None:
    if frozenset(value) != _RECORD_KEYS:
        raise KicadIndexArtifactError("kicad_index_record_shape_invalid")
    pins = _required_list(value, "pins")
    if any(frozenset(_required_mapping(pin)) != _PIN_KEYS for pin in pins):
        raise KicadIndexArtifactError("kicad_index_pin_shape_invalid")


def _read_bounded_regular_file(
    path: Path,
    maximum: int,
) -> tuple[bytes, tuple[int, int, int, int, int]]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_artifact_unavailable") from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise KicadIndexArtifactError("kicad_index_artifact_not_regular")
        if not 1 <= metadata.st_size <= maximum:
            raise KicadIndexArtifactError("kicad_index_artifact_size_invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise KicadIndexArtifactError("kicad_index_artifact_read_incomplete")
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        signature = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        )
        return content, signature
    finally:
        os.close(descriptor)


def _file_signature(path: Path) -> tuple[int, int, int, int, int]:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise KicadIndexArtifactError("kicad_index_artifact_unavailable") from error
    if stat.S_ISLNK(metadata.st_mode):
        raise KicadIndexArtifactError("kicad_index_artifact_symlink_forbidden")
    if not stat.S_ISREG(metadata.st_mode):
        raise KicadIndexArtifactError("kicad_index_artifact_not_regular")
    if not 1 <= metadata.st_size <= MAX_KICAD_INDEX_ARTIFACT_BYTES:
        raise KicadIndexArtifactError("kicad_index_artifact_size_invalid")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _absolute_artifact_path(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts or path.name in {"", ".", ".."}:
        raise KicadIndexArtifactError("kicad_index_artifact_path_invalid")
    return path


def _expected_revision(value: str) -> str:
    try:
        return require_commit_sha(value)
    except ValueError as error:
        raise KicadIndexArtifactError("kicad_index_expected_revision_invalid") from error


def _expected_digest(value: str) -> str:
    if _SHA256.fullmatch(value) is None:
        raise KicadIndexArtifactError("kicad_index_expected_digest_invalid")
    return value


def _validate_allowlist(values: tuple[str, ...]) -> tuple[str, ...]:
    try:
        KicadSymbolIndexer(values)
    except ValueError as error:
        raise KicadIndexArtifactError("kicad_index_allowlist_invalid") from error
    return values


def _library_allowed(library: str, allowlist: tuple[str, ...]) -> bool:
    return any(library == prefix or library.startswith(prefix) for prefix in allowlist)


def _library_name(path: str) -> str:
    parts = PurePosixPath(path).parts
    directory = next((item[:-13] for item in parts if item.endswith(".kicad_symdir")), None)
    return directory or PurePosixPath(path).stem


def _required_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise KicadIndexArtifactError("kicad_index_artifact_shape_invalid")
    return value


def _required_string(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise KicadIndexArtifactError("kicad_index_manifest_invalid")
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int) or isinstance(item, bool):
        raise KicadIndexArtifactError("kicad_index_manifest_invalid")
    return item


def _required_list(value: Mapping[str, object], key: str) -> list[object]:
    item = value.get(key)
    if not isinstance(item, list):
        raise KicadIndexArtifactError("kicad_index_artifact_shape_invalid")
    return list(item)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


if __name__ == "__main__":
    main()
