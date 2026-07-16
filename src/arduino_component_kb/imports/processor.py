"""Idempotent parser worker with Redis coordination and PostgreSQL truth."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import LockError, RedisError
from sqlalchemy.exc import IntegrityError

from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database
from arduino_component_kb.imports.adapters import DEFAULT_ADAPTERS
from arduino_component_kb.imports.domain import (
    ParserError,
    RetryableImportError,
    SourceFetchError,
)
from arduino_component_kb.imports.exact import ExactKeys
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.imports.repository import ImportRepository
from arduino_component_kb.imports.service import ComponentParser
from arduino_component_kb.imports.transport import SafeHttpFetcher


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
                now = datetime.now(UTC)
                if (
                    job.status == "running"
                    and job.updated_at > now - timedelta(seconds=settings.import_lock_ttl_seconds)
                ):
                    return
                job.status = "running"
                job.attempts += 1
                job.started_at = now
                job.next_retry_at = None
                job.updated_at = now
                submitted_url = job.submitted_url
            try:
                parsed = await ComponentParser(SafeHttpFetcher(), DEFAULT_ADAPTERS).parse(
                    submitted_url
                )
            except SourceFetchError as error:
                await _record_transient(repository, job_id)
                raise RetryableImportError(_backoff_ms(job.attempts)) from error
            except ParserError as error:
                async with session.begin():
                    locked = await repository.get_job(job_id, lock=True)
                    if locked is not None:
                        _mark_failed(locked, _safe_error_code(error))
                return

            lock = redis.lock(
                ExactKeys.from_parsed(parsed).lock_name,
                timeout=settings.import_lock_ttl_seconds,
                blocking_timeout=settings.import_lock_wait_seconds,
            )
            acquired = False
            try:
                acquired = await lock.acquire()
                if not acquired:
                    await _record_transient(repository, job_id)
                    raise RetryableImportError(_backoff_ms(job.attempts))
                async with session.begin():
                    locked = await repository.get_job(job_id, lock=True)
                    if locked is None or locked.status == "succeeded":
                        return
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


def _mark_failed(job: ImportJob, code: str) -> None:
    now = datetime.now(UTC)
    job.status = "failed"
    job.error_code = code[:80]
    job.finished_at = now
    job.updated_at = now


def _safe_error_code(error: ParserError) -> str:
    code = getattr(error, "code", "parser_rejected")
    return str(code).replace(" ", "_")[:80]


def _backoff_ms(attempt: int) -> int:
    value: int = 5_000 * (2 ** max(0, attempt - 1))
    return min(60_000, value)
