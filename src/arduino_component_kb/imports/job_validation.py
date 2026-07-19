"""Operator CLI for bounded end-to-end repository job validation."""

from __future__ import annotations

import argparse
import getpass
import json
import time
from dataclasses import dataclass
from typing import cast
from urllib.parse import urlsplit
from uuid import uuid4

import httpx2

from arduino_component_kb.imports.sample_validation import (
    KICAD_REQUESTED_REVISION,
    KICAD_SAMPLE_ENTRIES,
    KICAD_SAMPLE_PATH,
    SEEED_REQUESTED_REVISION,
    SEEED_SAMPLE_PATHS,
)

_TERMINAL_STATUSES = frozenset({"succeeded", "failed"})
_ACCEPTED_PARSE_STATUSES = frozenset({"parsed", "parsed_with_warnings"})


def sample_payloads() -> tuple[dict[str, str], ...]:
    seeed = tuple(
        {
            "source_key": "seeed_wiki",
            "revision": SEEED_REQUESTED_REVISION,
            "file_path": path,
        }
        for path in SEEED_SAMPLE_PATHS
    )
    kicad = tuple(
        {
            "source_key": "kicad_symbols",
            "revision": KICAD_REQUESTED_REVISION,
            "file_path": KICAD_SAMPLE_PATH,
            "entry_name": entry,
        }
        for entry in KICAD_SAMPLE_ENTRIES
    )
    return seeed + kicad


def validate_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("validation_base_url_invalid")
    if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("plain_http_is_only_allowed_for_loopback")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("validation_base_url_invalid")
    return value.rstrip("/") + "/"


@dataclass(slots=True)
class ApiClient:
    base_url: str
    client: httpx2.Client

    @classmethod
    def create(cls, base_url: str) -> ApiClient:
        validated = validate_base_url(base_url)
        return cls(
            validated,
            httpx2.Client(
                base_url=validated,
                timeout=35,
                follow_redirects=False,
                trust_env=False,
            ),
        )

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, str] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, object]:
        headers = {"Accept": "application/json"}
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
            headers["X-CSRF-Token"] = self.csrf_token()
        try:
            response = self.client.request(method, path, json=payload, headers=headers)
            response.raise_for_status()
            value = response.json()
        except httpx2.HTTPStatusError as error:
            detail = error.response.text[:1000]
            raise RuntimeError(
                f"api_request_failed:{error.response.status_code}:{detail}"
            ) from error
        except httpx2.HTTPError as error:
            raise RuntimeError("api_request_transport_failed") from error
        if not isinstance(value, dict):
            raise RuntimeError("api_response_invalid")
        return cast(dict[str, object], value)

    def csrf_token(self) -> str:
        token = self.client.cookies.get("ackb_csrf")
        if token is None:
            raise RuntimeError("csrf_cookie_missing")
        return token


def run_validation(base_url: str, login: str, timeout_seconds: int) -> dict[str, object]:
    client = ApiClient.create(base_url)
    password = getpass.getpass("Administrator password: ")
    client.request("POST", "/api/v1/auth/login", {"login": login, "password": password})
    password = ""

    submitted: list[tuple[str, str, dict[str, str]]] = []
    for payload in sample_payloads():
        key = str(uuid4())
        result = client.request(
            "POST", "/api/v1/import-jobs/repository", payload, idempotency_key=key
        )
        job_id = result.get("id")
        if not isinstance(job_id, str):
            raise RuntimeError("repository_job_id_missing")
        submitted.append((job_id, key, payload))

    first_id, first_key, first_payload = submitted[0]
    replay = client.request(
        "POST",
        "/api/v1/import-jobs/repository",
        first_payload,
        idempotency_key=first_key,
    )
    if replay.get("id") != first_id:
        raise RuntimeError("repository_job_idempotency_failed")

    deadline = time.monotonic() + timeout_seconds
    pending = {job_id for job_id, _, _ in submitted}
    completed: dict[str, dict[str, object]] = {}
    while pending and time.monotonic() < deadline:
        for job_id in tuple(pending):
            result = client.request("GET", f"/api/v1/import-jobs/{job_id}")
            status = result.get("status")
            if status in _TERMINAL_STATUSES:
                completed[job_id] = result
                pending.remove(job_id)
        if pending:
            time.sleep(1.5)
    if pending:
        raise RuntimeError(f"repository_jobs_timeout:{len(pending)}")

    safe_jobs: list[dict[str, object]] = []
    for job_id, _, payload in submitted:
        result = completed[job_id]
        revision = result.get("source_revision")
        if (
            result.get("status") != "succeeded"
            or result.get("parse_status") not in _ACCEPTED_PARSE_STATUSES
            or not isinstance(result.get("draft_component_id"), str)
            or not isinstance(revision, str)
            or len(revision) != 40
        ):
            code = result.get("error_code") or result.get("parse_status") or result.get("status")
            raise RuntimeError(f"repository_job_failed:{job_id}:{code}")
        safe_jobs.append(
            {
                "id": job_id,
                "source_key": payload["source_key"],
                "file_path": payload["file_path"],
                "entry_name": payload.get("entry_name"),
                "status": result["status"],
                "parse_status": result["parse_status"],
                "source_revision": revision,
                "draft_component_id": result["draft_component_id"],
            }
        )
    return {"ok": True, "job_count": len(safe_jobs), "idempotency_replay": True, "jobs": safe_jobs}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(
        description="Create and verify exactly 15 repository draft jobs through the HTTP API."
    )
    command.add_argument("--base-url", default="http://127.0.0.1:8000")
    command.add_argument("--login", default="admin")
    command.add_argument("--timeout-seconds", type=int, default=300, choices=range(30, 901))
    return command


def main() -> None:
    args = parser().parse_args()
    try:
        result = run_validation(args.base_url, args.login, args.timeout_seconds)
    except (RuntimeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
