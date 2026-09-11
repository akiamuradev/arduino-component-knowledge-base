"""Small JSON-only admin API; source files travel directly to private storage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.api.dependencies import (
    csrf_principal,
    database_session,
    require_permissions,
)
from arduino_component_kb.auth.domain import Permission, Principal
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.dispatch.repository import DispatchRepository
from arduino_component_kb.legacy.models import LegacyBundle, LegacyItem, LegacySourceLink
from arduino_component_kb.legacy.parser import SOURCE_NAME, XLSX_LIMIT, ZIP_LIMIT
from arduino_component_kb.legacy.planning import review_hash
from arduino_component_kb.media.storage import MediaStorage

router = APIRouter(prefix="/api/v1/legacy-imports", tags=["legacy-imports"])
admin = require_permissions(Permission.IMPORTS_BULK_APPLY)
Session = Annotated[AsyncSession, Depends(database_session)]
Admin = Annotated[Principal, Depends(admin)]
CSRF = Annotated[Principal, Depends(csrf_principal)]


class BundleInput(BaseModel):
    zip_size: int = Field(gt=0, le=ZIP_LIMIT)
    xlsx_size: int = Field(gt=0, le=XLSX_LIMIT)


class ApplyInput(BaseModel):
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmation: Literal["ИМПОРТ"]


class DecisionInput(BaseModel):
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["create", "merge", "skip"]
    merge_id: UUID | None = None


class LicenseInput(BaseModel):
    evidence: str = Field(min_length=30, max_length=4000)
    confirmation: Literal["ПРАВА ПРОВЕРЕНЫ"]


def key(bundle_id: UUID, kind: str) -> str:
    return f"bundles/{bundle_id}/{kind}"


async def audit(session: AsyncSession, actor: UUID, action: str, object_id: UUID) -> None:
    await AuthRepository(session).audit(
        now=datetime.now(UTC),
        actor_user_id=actor,
        action=f"legacy.{action}",
        object_type="legacy_bundle",
        object_id=object_id,
        request_id=None,
        outcome="success",
    )


async def locked_bundle(session: AsyncSession, bundle_id: UUID) -> LegacyBundle:
    bundle = await session.scalar(
        select(LegacyBundle)
        .where(
            LegacyBundle.id == bundle_id,
        )
        .with_for_update()
    )
    if bundle is None:
        raise HTTPException(404, detail={"code": "legacy_bundle_not_found"})
    return bundle


async def bundle_items(session: AsyncSession, bundle_id: UUID) -> list[LegacyItem]:
    return list(
        await session.scalars(
            select(LegacyItem)
            .where(
                LegacyItem.bundle_id == bundle_id,
            )
            .order_by(LegacyItem.position)
        )
    )


def conflict(code: str = "legacy_state_conflict") -> HTTPException:
    return HTTPException(409, detail={"code": code})


@router.post("", status_code=201)
async def create_bundle(
    body: BundleInput, request: Request, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, object]:
    # Serialize the small admission check so parallel requests cannot bypass it.
    await session.execute(text("SELECT pg_advisory_xact_lock(71842101)"))
    active = await session.scalar(
        select(func.count())
        .select_from(LegacyBundle)
        .where(
            LegacyBundle.status.in_(("uploading", "uploaded", "analyzing", "ready", "applying")),
        )
    )
    if active is not None and active >= 5:
        raise HTTPException(429, detail={"code": "legacy_pending_limit"})
    settings = cast(Settings, request.app.state.settings)
    storage = cast(MediaStorage, request.app.state.media_storage)
    now = datetime.now(UTC)
    bundle = LegacyBundle(
        id=uuid4(),
        owner_id=principal.user_id,
        status="uploading",
        zip_size=body.zip_size,
        xlsx_size=body.xlsx_size,
        created_at=now,
        updated_at=now,
    )
    session.add(bundle)
    urls = {
        kind: await storage.presigned_put(settings.minio_legacy_bucket, key(bundle.id, kind), 900)
        for kind in ("zip", "xlsx")
    }
    await audit(session, principal.user_id, "bundle_created", bundle.id)
    await session.commit()
    return {"id": str(bundle.id), "uploads": urls, "expires_seconds": 900}


@router.get("")
async def list_bundles(principal: Admin, session: Session) -> list[dict[str, object]]:
    rows = await session.scalars(
        select(LegacyBundle).order_by(LegacyBundle.created_at.desc()).limit(50)
    )
    return [
        {"id": str(b.id), "status": b.status, "created_at": b.created_at.isoformat()} for b in rows
    ]


@router.get("/{bundle_id}")
async def get_bundle(bundle_id: UUID, principal: Admin, session: Session) -> dict[str, object]:
    bundle = await session.get(LegacyBundle, bundle_id)
    if bundle is None:
        raise HTTPException(404, detail={"code": "legacy_bundle_not_found"})
    items = await bundle_items(session, bundle_id)
    return {
        "id": str(bundle.id),
        "source_name": SOURCE_NAME,
        "status": bundle.status,
        "phase": bundle.phase,
        "plan_hash": review_hash(bundle, items),
        "analysis_hash": bundle.plan_hash,
        "error_code": bundle.error_code,
        "statistics": bundle.statistics,
        "zip_sha256": bundle.zip_sha256,
        "xlsx_sha256": bundle.xlsx_sha256,
        "parser_version": bundle.parser_version,
        "items": [
            {
                "id": str(i.id),
                "target": i.payload,
                "candidates": i.candidates,
                "decision": i.decision,
                "status": i.status,
                "warnings": i.warnings,
                "error_code": i.error_code,
                "merge_id": str(i.merge_id) if i.merge_id else None,
                "result_id": str(i.result_id) if i.result_id else None,
            }
            for i in items
        ],
    }


@router.post("/{bundle_id}/uploaded")
async def complete_upload(
    bundle_id: UUID, request: Request, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, str]:
    bundle = await locked_bundle(session, bundle_id)
    if bundle.status != "uploading":
        raise conflict()
    storage = cast(MediaStorage, request.app.state.media_storage)
    settings = cast(Settings, request.app.state.settings)
    for kind, expected in (("zip", bundle.zip_size), ("xlsx", bundle.xlsx_size)):
        metadata = await storage.stat(settings.minio_legacy_bucket, key(bundle.id, kind))
        if metadata.size != expected:
            raise conflict("legacy_upload_size_mismatch")
    bundle.status = "uploaded"
    bundle.updated_at = datetime.now(UTC)
    await audit(session, principal.user_id, "upload_completed", bundle.id)
    await session.commit()
    return {"status": bundle.status}


@router.post("/{bundle_id}/analyze")
async def start_analysis(
    bundle_id: UUID, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, str]:
    bundle = await locked_bundle(session, bundle_id)
    if bundle.status != "uploaded":
        raise conflict()
    bundle.status = "analyzing"
    bundle.phase = "analysis"
    bundle.updated_at = datetime.now(UTC)
    DispatchRepository(session).add(
        job_type="legacy",
        job_id=bundle.id,
        queue_name="legacy",
        max_attempts=4,
        now=bundle.updated_at,
    )
    await audit(session, principal.user_id, "analysis_started", bundle.id)
    await session.commit()
    return {"status": bundle.status}


@router.patch("/{bundle_id}/items/{item_id}")
async def decide(
    bundle_id: UUID,
    item_id: UUID,
    body: DecisionInput,
    principal: Admin,
    csrf: CSRF,
    session: Session,
) -> dict[str, str]:
    bundle = await locked_bundle(session, bundle_id)
    items = await bundle_items(session, bundle_id)
    if bundle.status != "ready" or review_hash(bundle, items) != body.plan_hash:
        raise conflict("legacy_plan_changed")
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        raise HTTPException(404, detail={"code": "legacy_item_not_found"})
    item.merge_id = None
    item.merge_revision = None
    item.merge_edit_token = None
    if body.decision == "merge":
        candidate = next(
            (c for c in item.candidates if c["id"] == str(body.merge_id) and c["merge_allowed"]),
            None,
        )
        if candidate is None:
            raise conflict("legacy_merge_not_allowed")
        item.merge_id = body.merge_id
        item.merge_revision = int(str(candidate["revision"]))
        item.merge_edit_token = int(str(candidate["edit_token"]))
    item.decision = body.decision
    item.status = "planned"
    await audit(session, principal.user_id, "decision_changed", bundle.id)
    await session.commit()
    return {"plan_hash": review_hash(bundle, items)}


@router.post("/{bundle_id}/apply")
async def apply_bundle(
    bundle_id: UUID, body: ApplyInput, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, str]:
    bundle = await locked_bundle(session, bundle_id)
    items = await bundle_items(session, bundle_id)
    if bundle.status != "ready" or review_hash(bundle, items) != body.plan_hash:
        raise conflict("legacy_plan_changed")
    if not items or any(i.decision == "review" for i in items):
        raise conflict("legacy_review_required")
    bundle.confirmed_hash = body.plan_hash
    bundle.confirmed_by = principal.user_id
    bundle.status = "applying"
    bundle.phase = "apply"
    bundle.updated_at = datetime.now(UTC)
    await DispatchRepository(session).reset(
        job_type="legacy",
        job_id=bundle.id,
        queue_name="legacy",
        max_attempts=4,
        now=bundle.updated_at,
    )
    await audit(session, principal.user_id, "apply_confirmed", bundle.id)
    await session.commit()
    return {"status": bundle.status}


@router.post("/{bundle_id}/cancel")
async def cancel_bundle(
    bundle_id: UUID, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, str]:
    bundle = await locked_bundle(session, bundle_id)
    if bundle.status in {"completed", "cancelled"}:
        raise conflict()
    bundle.status = "cancelled"
    bundle.updated_at = datetime.now(UTC)
    await audit(session, principal.user_id, "cancelled", bundle.id)
    await session.commit()
    return {"status": bundle.status}


@router.post("/{bundle_id}/retry")
async def retry_bundle(
    bundle_id: UUID, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, str]:
    bundle = await locked_bundle(session, bundle_id)
    if bundle.status not in {"failed", "completed"}:
        raise conflict()
    items = await bundle_items(session, bundle_id)
    failed = [item for item in items if item.status == "failed"]
    if bundle.status == "completed" and not failed:
        raise conflict()
    if bundle.phase == "apply":
        if not bundle.confirmed_by or review_hash(bundle, items) != bundle.confirmed_hash:
            raise conflict("legacy_plan_changed")
        for item in failed:
            item.status = "planned"
            item.error_code = None
    bundle.status = "applying" if bundle.phase == "apply" else "analyzing"
    bundle.error_code = None
    bundle.updated_at = datetime.now(UTC)
    await DispatchRepository(session).reset(
        job_type="legacy",
        job_id=bundle.id,
        queue_name="legacy",
        max_attempts=4,
        now=bundle.updated_at,
    )
    await audit(session, principal.user_id, "retried", bundle.id)
    await session.commit()
    return {"status": bundle.status}


@router.get("/components/{component_id}/provenance")
async def provenance(
    component_id: UUID,
    principal: Annotated[Principal, Depends(require_permissions(Permission.COMPONENTS_EDIT))],
    session: Session,
) -> list[dict[str, object]]:
    rows = await session.scalars(
        select(LegacySourceLink).where(
            LegacySourceLink.component_id == component_id,
        )
    )
    return [
        {
            "identity": r.identity,
            "source_name": SOURCE_NAME,
            "license_status": r.license_status,
            "license_evidence": r.license_evidence,
        }
        for r in rows
    ]


@router.post("/components/{component_id}/license")
async def review_license(
    component_id: UUID, body: LicenseInput, principal: Admin, csrf: CSRF, session: Session
) -> dict[str, str]:
    rows = list(
        await session.scalars(
            select(LegacySourceLink)
            .where(
                LegacySourceLink.component_id == component_id,
            )
            .with_for_update()
        )
    )
    if not rows:
        raise HTTPException(404, detail={"code": "legacy_provenance_not_found"})
    for row in rows:
        row.license_status = "reviewed"
        row.license_evidence = body.evidence.strip()
        row.reviewed_by = principal.user_id
        row.reviewed_at = datetime.now(UTC)
    await audit(session, principal.user_id, "license_reviewed", component_id)
    await session.commit()
    return {"status": "reviewed"}
