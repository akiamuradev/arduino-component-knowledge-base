"""Durable administrator-only legacy bundles, plans and provenance.

Revision ID: 20260910_30
Revises: 20260910_29
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260910_30"
down_revision: str | None = "20260910_29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE legacy_bundles (
            id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES users(id),
            status VARCHAR(16) NOT NULL, phase VARCHAR(16) NOT NULL,
            zip_size INTEGER NOT NULL, xlsx_size INTEGER NOT NULL,
            zip_sha256 VARCHAR(64), xlsx_sha256 VARCHAR(64), parser_version VARCHAR(80),
            plan_hash VARCHAR(64), confirmed_hash VARCHAR(64), statistics JSONB NOT NULL,
            error_code VARCHAR(80), created_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT ck_legacy_bundle_status CHECK (status IN
                ('uploading','uploaded','analyzing','ready','applying','completed','failed','cancelled'))
        )
    """)
    op.create_index("ix_legacy_bundles_status", "legacy_bundles", ["status", "updated_at"])
    op.execute("""
        CREATE TABLE legacy_items (
            id UUID PRIMARY KEY, bundle_id UUID NOT NULL REFERENCES legacy_bundles(id),
            identity VARCHAR(64) NOT NULL, position INTEGER NOT NULL, payload JSONB NOT NULL,
            candidates JSONB NOT NULL, decision VARCHAR(16) NOT NULL,
            merge_id UUID REFERENCES components(id), merge_revision INTEGER,
            status VARCHAR(16) NOT NULL, result_id UUID REFERENCES components(id),
            warnings JSONB NOT NULL, error_code VARCHAR(80),
            CONSTRAINT ck_legacy_item_status CHECK
                (status IN ('planned','applying','applied','skipped','needs_review','failed')),
            CONSTRAINT ck_legacy_decision CHECK (decision IN ('create','merge','skip','review'))
        )
    """)
    op.create_index(
        "uq_legacy_items_identity", "legacy_items", ["bundle_id", "identity"], unique=True
    )
    op.execute("""
        CREATE TABLE legacy_source_links (
            identity VARCHAR(64) PRIMARY KEY, component_id UUID NOT NULL REFERENCES components(id),
            item_id UUID NOT NULL REFERENCES legacy_items(id), license_status VARCHAR(16) NOT NULL,
            license_evidence TEXT, reviewed_by UUID REFERENCES users(id), reviewed_at TIMESTAMPTZ
        )
    """)
    op.create_index("ix_legacy_source_links_component_id", "legacy_source_links", ["component_id"])
    _dispatch(True)


def _dispatch(legacy: bool) -> None:
    for name in ("type", "queue", "type_queue"):
        op.drop_constraint(f"ck_job_dispatches_{name}", "job_dispatches", type_="check")
    op.create_check_constraint(
        "ck_job_dispatches_type",
        "job_dispatches",
        "job_type IN ('import','media','legacy')" if legacy else "job_type IN ('import','media')",
    )
    op.create_check_constraint(
        "ck_job_dispatches_queue",
        "job_dispatches",
        "queue_name IN ('imports','images','videos','legacy')"
        if legacy
        else "queue_name IN ('imports','images','videos')",
    )
    condition = (
        "(job_type='import' AND queue_name='imports') OR "
        "(job_type='media' AND queue_name IN ('images','videos'))"
    )
    if legacy:
        condition += " OR (job_type='legacy' AND queue_name='legacy')"
    op.create_check_constraint("ck_job_dispatches_type_queue", "job_dispatches", condition)


def downgrade() -> None:
    # A downgrade must not silently discard queued work or imported provenance.
    op.execute("DELETE FROM job_dispatches WHERE job_type='legacy'")
    _dispatch(False)
    op.drop_table("legacy_source_links")
    op.drop_table("legacy_items")
    op.drop_table("legacy_bundles")
