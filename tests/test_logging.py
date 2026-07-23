"""Structured logging tests."""

from __future__ import annotations

import json
import logging

from arduino_component_kb.logging import JsonFormatter, normalize_request_id


def test_json_formatter_emits_only_bounded_fields() -> None:
    record = logging.LogRecord(
        name="arduino_component_kb.test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=10,
        msg="database_readiness_failed",
        args=(),
        exc_info=None,
    )
    record.request_id = "request-1"
    record.error_type = "ConnectionError"
    record.untrusted_detail = "postgresql://user:secret@example/database"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["event"] == "database_readiness_failed"
    assert payload["request_id"] == "request-1"
    assert payload["error_type"] == "ConnectionError"
    assert "untrusted_detail" not in payload
    assert "secret" not in json.dumps(payload)


def test_request_id_validation_is_bounded() -> None:
    assert normalize_request_id("safe_ID-1.2") == "safe_ID-1.2"
    assert normalize_request_id("x" * 129) != "x" * 129


def test_pipeline_logs_keep_correlation_and_state_but_drop_payloads() -> None:
    record = logging.LogRecord(
        name="arduino_component_kb.imports.pipeline",
        level=logging.INFO,
        pathname=__file__,
        lineno=40,
        msg="import_pipeline_stage_completed",
        args=(),
        exc_info=None,
    )
    record.import_run_id = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    record.import_stage = "normalization"
    record.attempt = 1
    record.outcome = "succeeded"
    record.shadow_mode = True
    record.quality_score = 840
    record.raw_source_payload = "secret source body"

    payload = json.loads(JsonFormatter().format(record))

    assert payload["import_run_id"] == "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    assert payload["import_stage"] == "normalization"
    assert payload["attempt"] == 1
    assert payload["shadow_mode"] is True
    assert payload["quality_score"] == 840
    assert "raw_source_payload" not in payload
    assert "secret source body" not in json.dumps(payload)
