"""Contract for the deliberately small live-source validation sample."""

from __future__ import annotations

import pytest

from arduino_component_kb.imports.job_validation import sample_payloads, validate_base_url
from arduino_component_kb.imports.sample_validation import (
    KICAD_REQUESTED_REVISION,
    KICAD_SAMPLE_ENTRIES,
    KICAD_SAMPLE_PATH,
    SEEED_SAMPLE_PATHS,
)


def test_live_repository_sample_is_fixed_and_bounded() -> None:
    assert len(SEEED_SAMPLE_PATHS) == 5
    assert len(set(SEEED_SAMPLE_PATHS)) == 5
    assert all(path.startswith("sites/en/docs/") for path in SEEED_SAMPLE_PATHS)
    assert all(path.endswith((".md", ".mdx")) for path in SEEED_SAMPLE_PATHS)
    assert KICAD_REQUESTED_REVISION == "9.0.9.1"
    assert KICAD_SAMPLE_PATH == "Sensor_Temperature.kicad_sym"
    assert len(KICAD_SAMPLE_ENTRIES) == 10
    assert len(set(KICAD_SAMPLE_ENTRIES)) == 10


def test_repository_job_sample_contains_exactly_fifteen_drafts() -> None:
    payloads = sample_payloads()
    assert len(payloads) == 15
    assert [item["source_key"] for item in payloads].count("seeed_wiki") == 5
    assert [item["source_key"] for item in payloads].count("kicad_symbols") == 10


def test_job_validation_rejects_credentials_and_remote_plain_http() -> None:
    assert validate_base_url("http://127.0.0.1:8000") == "http://127.0.0.1:8000/"
    assert validate_base_url("https://kb.example/base") == "https://kb.example/base/"
    with pytest.raises(ValueError, match="only_allowed_for_loopback"):
        validate_base_url("http://kb.example")
    with pytest.raises(ValueError, match="validation_base_url_invalid"):
        validate_base_url("https://user:password@kb.example")
