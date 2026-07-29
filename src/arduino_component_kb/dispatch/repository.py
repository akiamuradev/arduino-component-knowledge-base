"""PostgreSQL state machine for bounded Redis delivery and recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, cast
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.dispatch.models import JobDispatch
from arduino_component_kb.imports.models import ImportJob
from arduino_component_kb.media.models import MediaAsset, MediaJob

JobType = Literal["import", "media"]
QueueName = Literal["imports", "images", "videos"]


@dataclass(frozen=True, slots=True)
class DispatchIntent:
    id: UUID
    job_type: JobType
    job_id: UUID
    queue_name: QueueName
    attempt: int


class DispatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(
        self,
        *,
        job_type: JobType,
        job_id: UUID,
        queue_name: QueueName,
        max_attempts: int,
        now: datetime,
    ) -> JobDispatch:
        dispatch = JobDispatch(
            id=uuid4(),
            job_type=job_type,
            job_id=job_id,
            queue_name=queue_name,
            status="pending",
            attempts=0,
            max_attempts=max_attempts,
            next_attempt_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(dispatch)
        return dispatch

    async def reset(
        self,
        *,
        job_type: JobType,
        job_id: UUID,
        queue_name: QueueName,
        max_attempts: int,
        now: datetime,
    ) -> JobDispatch:
        dispatch = cast(
            JobDispatch | None,
            await self.session.scalar(
                select(JobDispatch)
                .where(
                    JobDispatch.job_type == job_type,
                    JobDispatch.job_id == job_id,
                )
                .with_for_update()
            ),
        )
        if dispatch is None:
            return self.add(
                job_type=job_type,
                job_id=job_id,
                queue_name=queue_name,
                max_attempts=max_attempts,
                now=now,
            )
        dispatch.queue_name = queue_name
        dispatch.status = "pending"
        dispatch.attempts = 0
        dispatch.max_attempts = max_attempts
        dispatch.next_attempt_at = now
        dispatch.last_attempt_at = None
        dispatch.delivered_at = None
        dispatch.error_code = None
        dispatch.updated_at = now
        return dispatch

    async def recover_lost_deliveries(
        self,
        *,
        now: datetime,
        stale_delivery_seconds: int,
        import_lease_seconds: int,
        media_lease_seconds: int,
        limit: int,
    ) -> int:
        recovered = 0
        recovered += await self._recover_imports(
            now=now,
            stale_delivery_seconds=stale_delivery_seconds,
            lease_seconds=import_lease_seconds,
            limit=limit,
        )
        remaining = max(0, limit - recovered)
        if remaining:
            recovered += await self._recover_media(
                now=now,
                stale_delivery_seconds=stale_delivery_seconds,
                lease_seconds=media_lease_seconds,
                limit=remaining,
            )
        if recovered:
            await self.session.flush()
        return recovered

    async def _recover_imports(
        self,
        *,
        now: datetime,
        stale_delivery_seconds: int,
        lease_seconds: int,
        limit: int,
    ) -> int:
        stale_delivery = now - timedelta(seconds=stale_delivery_seconds)
        stale_lease = now - timedelta(seconds=lease_seconds)
        rows = (
            await self.session.execute(
                select(JobDispatch, ImportJob)
                .join(
                    ImportJob,
                    (JobDispatch.job_type == "import") & (JobDispatch.job_id == ImportJob.id),
                )
                .where(
                    JobDispatch.status == "delivered",
                    or_(
                        (ImportJob.status == "queued")
                        & (JobDispatch.delivered_at <= stale_delivery),
                        (ImportJob.status == "retrying")
                        & (ImportJob.next_retry_at.is_not(None))
                        & (ImportJob.next_retry_at <= now),
                        (ImportJob.status == "running")
                        & (
                            ImportJob.heartbeat_at.is_(None)
                            | (ImportJob.heartbeat_at <= stale_lease)
                        ),
                    ),
                )
                .order_by(JobDispatch.updated_at, JobDispatch.id)
                .limit(limit)
                .with_for_update(of=(JobDispatch, ImportJob), skip_locked=True)
            )
        ).all()
        for dispatch, job in rows:
            if dispatch.attempts >= dispatch.max_attempts:
                self._fail_import(dispatch, job, now)
            else:
                self._make_pending(dispatch, now)
        return len(rows)

    async def _recover_media(
        self,
        *,
        now: datetime,
        stale_delivery_seconds: int,
        lease_seconds: int,
        limit: int,
    ) -> int:
        stale_delivery = now - timedelta(seconds=stale_delivery_seconds)
        stale_lease = now - timedelta(seconds=lease_seconds)
        rows = (
            await self.session.execute(
                select(JobDispatch, MediaJob, MediaAsset)
                .join(
                    MediaJob,
                    (JobDispatch.job_type == "media") & (JobDispatch.job_id == MediaJob.id),
                )
                .join(MediaAsset, MediaAsset.id == MediaJob.asset_id)
                .where(
                    JobDispatch.status == "delivered",
                    or_(
                        (MediaJob.status == "queued")
                        & (JobDispatch.delivered_at <= stale_delivery),
                        (MediaJob.status == "retrying")
                        & (MediaJob.next_retry_at.is_not(None))
                        & (MediaJob.next_retry_at <= now),
                        (MediaJob.status == "running")
                        & (
                            MediaJob.heartbeat_at.is_(None) | (MediaJob.heartbeat_at <= stale_lease)
                        ),
                    ),
                )
                .order_by(JobDispatch.updated_at, JobDispatch.id)
                .limit(limit)
                .with_for_update(
                    of=(JobDispatch, MediaJob, MediaAsset),
                    skip_locked=True,
                )
            )
        ).all()
        for dispatch, job, asset in rows:
            if dispatch.attempts >= dispatch.max_attempts:
                self._fail_media(dispatch, job, asset, now)
            else:
                self._make_pending(dispatch, now)
        return len(rows)

    async def claim_due(
        self,
        *,
        now: datetime,
        limit: int,
        claim_lease_seconds: int,
    ) -> tuple[DispatchIntent, ...]:
        rows = tuple(
            (
                await self.session.scalars(
                    select(JobDispatch)
                    .where(
                        JobDispatch.status == "pending",
                        JobDispatch.next_attempt_at <= now,
                        JobDispatch.attempts < JobDispatch.max_attempts,
                    )
                    .order_by(JobDispatch.next_attempt_at, JobDispatch.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        intents: list[DispatchIntent] = []
        for dispatch in rows:
            dispatch.attempts += 1
            dispatch.last_attempt_at = now
            dispatch.next_attempt_at = now + timedelta(seconds=claim_lease_seconds)
            dispatch.updated_at = now
            intents.append(
                DispatchIntent(
                    id=dispatch.id,
                    job_type=cast(JobType, dispatch.job_type),
                    job_id=dispatch.job_id,
                    queue_name=cast(QueueName, dispatch.queue_name),
                    attempt=dispatch.attempts,
                )
            )
        return tuple(intents)

    async def mark_delivered(self, dispatch_id: UUID, now: datetime) -> None:
        dispatch = await self._locked(dispatch_id)
        if dispatch is None or dispatch.status != "pending":
            return
        if not await self._job_is_active(dispatch):
            dispatch.status = "delivered"
            dispatch.delivered_at = now
            dispatch.next_attempt_at = now
            dispatch.error_code = None
            dispatch.updated_at = now
            return
        dispatch.status = "delivered"
        dispatch.delivered_at = now
        dispatch.next_attempt_at = now
        dispatch.error_code = None
        dispatch.updated_at = now
        if dispatch.job_type == "media":
            job = await self.session.get(MediaJob, dispatch.job_id)
            if job is not None:
                job.last_enqueued_at = now
                job.updated_at = now

    async def mark_delivery_failed(self, dispatch_id: UUID, now: datetime) -> None:
        dispatch = await self._locked(dispatch_id)
        if dispatch is None or dispatch.status != "pending":
            return
        if not await self._job_is_active(dispatch):
            dispatch.status = "delivered"
            dispatch.delivered_at = now
            dispatch.next_attempt_at = now
            dispatch.error_code = None
            dispatch.updated_at = now
            return
        if dispatch.attempts >= dispatch.max_attempts:
            if dispatch.job_type == "import":
                import_job = cast(
                    ImportJob | None,
                    await self.session.scalar(
                        select(ImportJob).where(ImportJob.id == dispatch.job_id).with_for_update()
                    ),
                )
                if import_job is not None:
                    self._fail_import(dispatch, import_job, now)
            else:
                row = (
                    await self.session.execute(
                        select(MediaJob, MediaAsset)
                        .join(MediaAsset, MediaAsset.id == MediaJob.asset_id)
                        .where(MediaJob.id == dispatch.job_id)
                        .with_for_update(of=(MediaJob, MediaAsset))
                    )
                ).one_or_none()
                if row is not None:
                    media_job, asset = row.tuple()
                    self._fail_media(dispatch, media_job, asset, now)
            return
        dispatch.error_code = "broker_unavailable"
        dispatch.next_attempt_at = now + timedelta(seconds=self._backoff_seconds(dispatch.attempts))
        dispatch.updated_at = now

    async def _locked(self, dispatch_id: UUID) -> JobDispatch | None:
        return cast(
            JobDispatch | None,
            await self.session.scalar(
                select(JobDispatch).where(JobDispatch.id == dispatch_id).with_for_update()
            ),
        )

    async def _job_is_active(self, dispatch: JobDispatch) -> bool:
        if dispatch.job_type == "import":
            status = await self.session.scalar(
                select(ImportJob.status).where(ImportJob.id == dispatch.job_id)
            )
            return status in {"queued", "running", "retrying"}
        status = await self.session.scalar(
            select(MediaJob.status).where(MediaJob.id == dispatch.job_id)
        )
        return status in {"queued", "running", "retrying"}

    @staticmethod
    def _make_pending(dispatch: JobDispatch, now: datetime) -> None:
        dispatch.status = "pending"
        dispatch.next_attempt_at = now
        dispatch.error_code = None
        dispatch.updated_at = now

    @staticmethod
    def _fail_import(dispatch: JobDispatch, job: ImportJob, now: datetime) -> None:
        dispatch.status = "failed"
        dispatch.error_code = "dispatch_attempts_exhausted"
        dispatch.next_attempt_at = now
        dispatch.updated_at = now
        if job.status in {"queued", "running", "retrying"}:
            job.status = "failed"
            job.error_code = "import_dispatch_exhausted"
            job.next_retry_at = None
            job.finished_at = now
            job.heartbeat_at = now
            job.updated_at = now

    @staticmethod
    def _fail_media(
        dispatch: JobDispatch,
        job: MediaJob,
        asset: MediaAsset,
        now: datetime,
    ) -> None:
        dispatch.status = "failed"
        dispatch.error_code = "dispatch_attempts_exhausted"
        dispatch.next_attempt_at = now
        dispatch.updated_at = now
        if job.status in {"queued", "running", "retrying"}:
            job.status = "failed"
            job.phase = "failed"
            job.error_code = "media_dispatch_exhausted"
            job.next_retry_at = None
            job.finished_at = now
            job.heartbeat_at = now
            job.updated_at = now
            asset.status = "rejected"
            asset.failure_code = "media_dispatch_exhausted"
            asset.updated_at = now

    @staticmethod
    def _backoff_seconds(attempt: int) -> int:
        value: int = 5 * (2 ** max(0, attempt - 1))
        return min(60, value)
