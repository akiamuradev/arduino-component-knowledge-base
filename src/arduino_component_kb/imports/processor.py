"""Idempotent parser worker with Redis coordination and PostgreSQL truth."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from time import perf_counter
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import LockError, RedisError
from sqlalchemy.exc import IntegrityError

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.imports.acquisition import (
    AcquisitionPolicy,
    RepositoryAcquirer,
    RepositoryAcquisitionError,
)
from arduino_component_kb.imports.adapters import DEFAULT_ADAPTERS
from arduino_component_kb.imports.adapters.kicad_symbols import KicadSymbolsAdapter
from arduino_component_kb.imports.adapters.seeed_wiki import SeeedWikiAdapter
from arduino_component_kb.imports.domain import (
    ParserError,
    RetryableImportError,
    SourceFetchError,
)
from arduino_component_kb.imports.exact import ExactKeys
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.imports.repository import ImportRepository
from arduino_component_kb.imports.repository_domain import (
    ParseStatus,
    RepositoryEntry,
)
from arduino_component_kb.imports.service import ComponentParser
from arduino_component_kb.imports.transport import SafeHttpFetcher

logger = logging.getLogger("arduino_component_kb.imports")


async def process_import_job(job_id: UUID, settings: Settings) -> None:
    database = Database(settings)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with database.sessions() as session:
            repository = ImportRepository(session)
            async with session.begin():
                job = await repository.get_job(job_id, lock=True)
                if job is None or job.status == "succeeded" or job.attempts >= job.max_attempts:
                    return
                source = await repository.active_source(job.source_id)
                if source is None:
                    _mark_failed(job, "source_disabled")
                    return
                now = datetime.now(UTC)
                if job.status == "running" and job.updated_at > now - timedelta(
                    seconds=settings.import_lock_ttl_seconds
                ):
                    return
                job.status = "running"
                job.attempts += 1
                job.started_at = now
                job.next_retry_at = None
                job.updated_at = now
                job.heartbeat_at = now
                submitted_url = job.submitted_url
                is_repository_job = job.repository_url is not None
                requested_revision = job.requested_revision
                source_file_path = job.source_file_path
                source_entry_name = job.source_entry_name
                attempt = job.attempts
            if is_repository_job:
                acquisition_started = perf_counter()
                if requested_revision is None or source_file_path is None:
                    async with session.begin():
                        locked = await repository.get_job(job_id, lock=True)
                        if locked is not None:
                            _mark_failed(locked, "repository_job_invalid")
                    return
                try:
                    acquired_entry = await RepositoryAcquirer(
                        policy=AcquisitionPolicy(
                            connect_timeout_seconds=settings.repository_connect_timeout_seconds,
                            read_timeout_seconds=settings.repository_read_timeout_seconds,
                            total_timeout_seconds=settings.repository_total_timeout_seconds,
                            max_response_bytes=settings.repository_max_response_bytes,
                            max_file_bytes=settings.repository_max_file_bytes,
                        )
                    ).acquire(
                        source.key,
                        source.repository_url or "",
                        requested_revision,
                        source_file_path,
                    )
                    entry = RepositoryEntry(acquired_entry.file_path, source_entry_name)
                    adapter = (
                        SeeedWikiAdapter()
                        if source.key == "seeed_wiki"
                        else KicadSymbolsAdapter(settings.kicad_library_prefixes)
                    )
                    await adapter.validate_revision(acquired_entry.snapshot.revision)
                    parsed_repository = await adapter.parse_entry(
                        acquired_entry.snapshot, entry, parsed_at=datetime.now(UTC)
                    )
                except RepositoryAcquisitionError as error:
                    if error.retryable:
                        await _record_transient(repository, job_id)
                        raise RetryableImportError(_backoff_ms(attempt)) from error
                    async with session.begin():
                        locked = await repository.get_job(job_id, lock=True)
                        if locked is not None:
                            _mark_failed(locked, error.code)
                    return
                except ValueError as error:
                    async with session.begin():
                        locked = await repository.get_job(job_id, lock=True)
                        if locked is not None:
                            _mark_failed(locked, _safe_value_code(error))
                    return
                if parsed_repository.status not in {
                    ParseStatus.PARSED,
                    ParseStatus.PARSED_WITH_WARNINGS,
                }:
                    async with session.begin():
                        locked = await repository.get_job(job_id, lock=True)
                        if locked is not None:
                            locked.parse_status = parsed_repository.status.value
                            locked.warnings_json = list(parsed_repository.warnings)
                            _mark_failed(locked, f"repository_{parsed_repository.status.value}")
                    return
                lock_name = (
                    "ackb:import:repository:"
                    + sha256(parsed_repository.idempotency_key.encode()).hexdigest()
                )
                logger.info(
                    "repository_entry_parsed",
                    extra={
                        "source": source.key,
                        "revision": parsed_repository.source_revision,
                        "adapter_version": parsed_repository.parser_version,
                        "files_scanned": 1,
                        "entries_discovered": 1,
                        "entries_parsed": 1,
                        "warnings_count": len(parsed_repository.warnings),
                        "failed_count": 0,
                        "bytes_downloaded": acquired_entry.bytes_downloaded,
                        "duration_ms": round((perf_counter() - acquisition_started) * 1000, 3),
                    },
                )
            else:
                parsed_repository = None
            try:
                if is_repository_job:
                    parsed = None
                else:
                    parsed = await ComponentParser(SafeHttpFetcher(), DEFAULT_ADAPTERS).parse(
                        submitted_url
                    )
            except SourceFetchError as error:
                await _record_transient(repository, job_id)
                raise RetryableImportError(_backoff_ms(attempt)) from error
            except ParserError as error:
                async with session.begin():
                    locked = await repository.get_job(job_id, lock=True)
                    if locked is not None:
                        _mark_failed(locked, _safe_error_code(error))
                return

            if parsed_repository is None:
                if parsed is None:
                    raise RuntimeError("import_parser_result_missing")
                lock_name = ExactKeys.from_parsed(parsed).lock_name
            lock = redis.lock(
                lock_name,
                timeout=settings.import_lock_ttl_seconds,
                blocking_timeout=settings.import_lock_wait_seconds,
            )
            acquired = False
            try:
                acquired = await lock.acquire()
                if not acquired:
                    await _record_transient(repository, job_id)
                    raise RetryableImportError(_backoff_ms(attempt))
                async with session.begin():
                    locked = await repository.get_job(job_id, lock=True)
                    if locked is None or locked.status == "succeeded":
                        return
                    if parsed_repository is not None:
                        locked.heartbeat_at = datetime.now(UTC)
                        locked.metrics_json = {
                            "files_scanned": 1,
                            "entries_discovered": 1,
                            "entries_parsed": 1,
                            "warnings_count": len(parsed_repository.warnings),
                            "failed_count": 0,
                            "bytes_downloaded": acquired_entry.bytes_downloaded,
                            "duration_ms": round((perf_counter() - acquisition_started) * 1000, 3),
                        }
                        await repository.persist_repository_draft(locked, source, parsed_repository)
                    elif parsed is not None:
                        await repository.persist_draft(locked, parsed)
                    await session.flush()
            except IntegrityError as error:
                await session.rollback()
                await _record_transient(repository, job_id)
                raise RetryableImportError(_backoff_ms(job.attempts)) from error
            except RedisError as error:
                await _record_transient(repository, job_id)
                raise RetryableImportError(_backoff_ms(job.attempts)) from error
            finally:
                if acquired:
                    try:
                        await lock.release()
                    except (LockError, RedisError):
                        pass
    finally:
        await redis.aclose()
        await database.dispose()


async def _record_transient(repository: ImportRepository, job_id: UUID) -> None:
    async with repository.session.begin():
        job = await repository.get_job(job_id, lock=True)
        if job is None or job.status == "succeeded":
            return
        now = datetime.now(UTC)
        if job.attempts >= job.max_attempts:
            _mark_failed(job, "import_retry_exhausted")
        else:
            job.status = "retrying"
            job.error_code = "import_transient_failure"
            job.next_retry_at = now + timedelta(milliseconds=_backoff_ms(job.attempts))
            job.updated_at = now
            job.heartbeat_at = now


def _mark_failed(job: ImportJob, code: str) -> None:
    now = datetime.now(UTC)
    job.status = "failed"
    job.error_code = code[:80]
    job.finished_at = now
    job.updated_at = now
    job.heartbeat_at = now


def _safe_error_code(error: ParserError) -> str:
    code = getattr(error, "code", "parser_rejected")
    return str(code).replace(" ", "_")[:80]


def _safe_value_code(error: ValueError) -> str:
    code = str(error) or "repository_parser_rejected"
    if not all(
        character.islower() or character.isdigit() or character == "_" for character in code
    ):
        return "repository_parser_rejected"
    return code[:80]


def _backoff_ms(attempt: int) -> int:
    value: int = 5_000 * (2 ** max(0, attempt - 1))
    return min(60_000, value)
