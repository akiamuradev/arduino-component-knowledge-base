"""Stage 13.1 immutable KiCad index artifact and loader tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from import_pipeline_helpers import KICAD_FIXTURES, KICAD_REVISION, kicad_snapshot

from arduino_component_kb.imports.pipeline import (
    KICAD_INDEX_ARTIFACT_SCHEMA,
    KicadIndexArtifactError,
    KicadIndexArtifactLoader,
    KicadIndexSourceSnapshot,
    build_kicad_index_artifact,
    deserialize_kicad_index_artifact,
    publish_kicad_index_artifact,
    snapshot_from_directory,
)


def test_artifact_round_trip_is_deterministic_and_non_empty() -> None:
    first = build_kicad_index_artifact(kicad_snapshot())
    second = build_kicad_index_artifact(kicad_snapshot())

    assert first.content == second.content
    assert first.loaded.manifest.schema_version == KICAD_INDEX_ARTIFACT_SCHEMA
    assert first.loaded.manifest.source_revision == KICAD_REVISION
    assert first.loaded.manifest.symbol_count == len(first.loaded.index.records) == 10
    assert first.loaded.manifest.index_sha256 == first.loaded.index.index_sha256
    loaded = deserialize_kicad_index_artifact(
        first.content,
        expected_revision=KICAD_REVISION,
        expected_sha256=first.loaded.manifest.index_sha256,
    )
    assert loaded == first.loaded


def test_loader_reuses_only_the_same_verified_file_identity(tmp_path: Path) -> None:
    built = build_kicad_index_artifact(kicad_snapshot())
    artifact_path = tmp_path / "index.json"
    publish_kicad_index_artifact(artifact_path, built.content)
    loader = KicadIndexArtifactLoader()

    first = loader.load(
        artifact_path,
        expected_revision=KICAD_REVISION,
        expected_sha256=built.loaded.manifest.index_sha256,
    )
    cached = loader.load(
        artifact_path,
        expected_revision=KICAD_REVISION,
        expected_sha256=built.loaded.manifest.index_sha256,
    )
    second_process_loader = KicadIndexArtifactLoader().load(
        artifact_path,
        expected_revision=KICAD_REVISION,
        expected_sha256=built.loaded.manifest.index_sha256,
    )

    assert first is cached
    assert first == second_process_loader
    assert first.index.index_sha256 == built.loaded.index.index_sha256


def test_loader_rejects_revision_digest_payload_and_allowlist_mismatch(
    tmp_path: Path,
) -> None:
    built = build_kicad_index_artifact(kicad_snapshot())
    artifact_path = tmp_path / "index.json"
    publish_kicad_index_artifact(artifact_path, built.content)

    with pytest.raises(KicadIndexArtifactError, match="kicad_index_revision_mismatch"):
        KicadIndexArtifactLoader().load(
            artifact_path,
            expected_revision="c" * 40,
            expected_sha256=built.loaded.manifest.index_sha256,
        )
    with pytest.raises(KicadIndexArtifactError, match="kicad_index_digest_mismatch"):
        KicadIndexArtifactLoader().load(
            artifact_path,
            expected_revision=KICAD_REVISION,
            expected_sha256="d" * 64,
        )
    with pytest.raises(KicadIndexArtifactError, match="kicad_index_library_not_allowed"):
        KicadIndexArtifactLoader().load(
            artifact_path,
            expected_revision=KICAD_REVISION,
            expected_sha256=built.loaded.manifest.index_sha256,
            library_allowlist=("Sensor_",),
        )

    payload = json.loads(built.content)
    payload["records"][0]["description"] = "tampered"
    tampered = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    with pytest.raises(KicadIndexArtifactError, match="kicad_index_payload_digest_mismatch"):
        deserialize_kicad_index_artifact(
            tampered,
            expected_revision=KICAD_REVISION,
            expected_sha256=built.loaded.manifest.index_sha256,
        )


def test_publish_is_atomic_idempotent_and_never_overwrites_a_version(
    tmp_path: Path,
) -> None:
    built = build_kicad_index_artifact(kicad_snapshot())
    output = tmp_path / "index.json"

    assert publish_kicad_index_artifact(output, built.content) == output
    assert publish_kicad_index_artifact(output, built.content) == output
    assert output.read_bytes() == built.content
    assert not tuple(tmp_path.glob("*.tmp"))
    with pytest.raises(KicadIndexArtifactError, match="kicad_index_artifact_exists"):
        publish_kicad_index_artifact(output, built.content + b" ")


def test_publish_maps_inaccessible_output_to_a_safe_code(tmp_path: Path) -> None:
    built = build_kicad_index_artifact(kicad_snapshot())
    blocked = tmp_path / "blocked"
    blocked.mkdir(mode=0o700)
    blocked.chmod(0)
    try:
        with pytest.raises(KicadIndexArtifactError, match="kicad_index_output_unavailable"):
            publish_kicad_index_artifact(blocked / "index.json", built.content)
    finally:
        blocked.chmod(0o700)


def test_loader_and_snapshot_builder_reject_symlinks(tmp_path: Path) -> None:
    built = build_kicad_index_artifact(kicad_snapshot())
    real_artifact = tmp_path / "real.json"
    real_artifact.write_bytes(built.content)
    artifact_link = tmp_path / "index.json"
    artifact_link.symlink_to(real_artifact)

    with pytest.raises(KicadIndexArtifactError, match="kicad_index_artifact_symlink_forbidden"):
        KicadIndexArtifactLoader().load(
            artifact_link,
            expected_revision=KICAD_REVISION,
            expected_sha256=built.loaded.manifest.index_sha256,
        )

    snapshot_root = tmp_path / "snapshot"
    snapshot_root.mkdir()
    (snapshot_root / "Sensor_Link.kicad_sym").symlink_to(
        KICAD_FIXTURES / "Sensor_Temperature.kicad_sym"
    )
    with pytest.raises(KicadIndexArtifactError, match="kicad_index_snapshot_symlink_forbidden"):
        snapshot_from_directory(snapshot_root, KICAD_REVISION)


def test_directory_builder_uses_only_allowlisted_bounded_libraries() -> None:
    snapshot = snapshot_from_directory(KICAD_FIXTURES, KICAD_REVISION)
    built = build_kicad_index_artifact(snapshot)

    paths = tuple(item.source_path for item in built.loaded.manifest.libraries)
    assert "Audio_Outside.kicad_sym" not in paths
    assert "Display_Graphic.kicad_sym" in paths
    assert built.loaded.manifest.symbol_count == 10

    with pytest.raises(KicadIndexArtifactError, match="kicad_index_file_limit_exceeded"):
        snapshot_from_directory(KICAD_FIXTURES, KICAD_REVISION, max_files=1)


def test_index_snapshot_has_separate_bounded_capacity_from_card_imports() -> None:
    content = b"x" * (2 * 1024 * 1024 + 1)
    snapshot = KicadIndexSourceSnapshot(
        "https://gitlab.com/kicad/libraries/kicad-symbols",
        KICAD_REVISION,
        {"Sensor_Large.kicad_sym": content},
    )

    assert snapshot.files["Sensor_Large.kicad_sym"] == content
