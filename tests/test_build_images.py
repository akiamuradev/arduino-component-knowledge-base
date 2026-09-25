"""Release builder provenance without Docker or deployment."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.build_images import build_environment


def test_release_builder_uses_project_version_and_actual_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ACKB_APP_VERSION", "1.0.1")
    monkeypatch.setenv("ACKB_BUILD_GIT_SHA", "b" * 40)
    root = Path(__file__).resolve().parents[1]
    with patch("scripts.build_images.subprocess.check_output", side_effect=["", "a" * 40]):
        env = build_environment(root)
    assert env["ACKB_APP_VERSION"] == "1.7.5"
    assert env["ACKB_BUILD_GIT_SHA"] == "a" * 40


def test_release_builder_rejects_uncommitted_sources() -> None:
    with patch(
        "scripts.build_images.subprocess.check_output", return_value=" M frontend/src/app.ts"
    ):
        with pytest.raises(SystemExit, match="working-tree changes"):
            build_environment(Path("unused"))


def test_release_builder_rejects_mismatched_license_copy() -> None:
    root = Path(__file__).resolve().parents[1]
    with (
        patch("scripts.build_images.subprocess.check_output", return_value=""),
        patch("scripts.build_images.Path.read_bytes", side_effect=[b"canonical", b"stale"]),
    ):
        with pytest.raises(SystemExit, match="license copy differs"):
            build_environment(root)
