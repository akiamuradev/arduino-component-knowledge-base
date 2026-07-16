"""Add licensed repository sources and immutable provenance snapshots.

Revision ID: 20260716_13
Revises: 20260716_12
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260716_13"
down_revision: str | None = "20260716_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("sources_allowed_host_key", "sources", type_="unique")
    op.alter_column("sources", "allowed_host", existing_type=sa.String(253), nullable=True)
    op.add_column(
        "sources",
        sa.Column("display_name", sa.String(160), nullable=False, server_default="Imported source"),
    )
    op.add_column(
        "sources", sa.Column("source_type", sa.String(24), nullable=False, server_default="website")
    )
    op.add_column(
        "sources", sa.Column("status", sa.String(16), nullable=False, server_default="inactive")
    )
    op.add_column("sources", sa.Column("repository_url", sa.String(500)))
    op.add_column("sources", sa.Column("repository_owner", sa.String(160)))
    op.add_column("sources", sa.Column("repository_name", sa.String(160)))
    op.add_column(
        "sources",
        sa.Column(
            "default_revision_policy",
            sa.String(32),
            nullable=False,
            server_default="immutable_commit",
        ),
    )
    op.add_column("sources", sa.Column("license_name", sa.String(160)))
    op.add_column("sources", sa.Column("license_spdx", sa.String(80)))
    op.add_column("sources", sa.Column("license_url", sa.String(500)))
    op.add_column(
        "sources",
        sa.Column("permission_status", sa.String(24), nullable=False, server_default="unknown"),
    )
    op.add_column(
        "sources",
        sa.Column("content_policy", sa.String(64), nullable=False, server_default="metadata_only"),
    )
    op.add_column("sources", sa.Column("disable_reason", sa.String(160)))
    op.add_column(
        "sources",
        sa.Column("allow_text_import", sa.String(16), nullable=False, server_default="none"),
    )
    for column in (
        "allow_facts_import",
        "allow_media_import",
        "allow_code_import",
        "allow_attachment_import",
    ):
        op.add_column(
            "sources", sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false())
        )
    op.create_check_constraint(
        "ck_sources_type",
        "sources",
        "source_type IN ('website','git_repository','official_library')",
    )
    op.create_check_constraint(
        "ck_sources_status", "sources", "status IN ('active','inactive','disabled')"
    )
    op.create_check_constraint(
        "ck_sources_revision_policy",
        "sources",
        "default_revision_policy IN ('immutable_commit','release_tag')",
    )
    op.create_check_constraint(
        "ck_sources_permission",
        "sources",
        "permission_status IN ('unknown','denied','license_granted')",
    )
    op.create_check_constraint(
        "ck_sources_text_import", "sources", "allow_text_import IN ('none','limited','full')"
    )
    op.create_check_constraint(
        "ck_sources_repository_identity",
        "sources",
        "source_type = 'website' OR (repository_url IS NOT NULL "
        "AND repository_owner IS NOT NULL AND repository_name IS NOT NULL)",
    )
    op.create_index(
        "uq_sources_repository_url",
        "sources",
        ["repository_url"],
        unique=True,
        postgresql_where=sa.text("repository_url IS NOT NULL"),
    )

    op.add_column("component_sources", sa.Column("source_revision", sa.String(64)))
    op.add_column("component_sources", sa.Column("source_tag", sa.String(100)))
    op.add_column("component_sources", sa.Column("source_file_path", sa.String(1000)))
    op.add_column("component_sources", sa.Column("source_entry_name", sa.String(300)))
    op.add_column("component_sources", sa.Column("original_url", sa.String(1000)))
    op.add_column("component_sources", sa.Column("imported_at", sa.DateTime(timezone=True)))
    op.add_column(
        "component_sources",
        sa.Column(
            "imported_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "component_sources",
        sa.Column(
            "provenance_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column("component_sources", sa.Column("modifications_notice", sa.String(1000)))
    op.add_column("component_sources", sa.Column("license_snapshot_name", sa.String(160)))
    op.add_column("component_sources", sa.Column("license_snapshot_spdx", sa.String(80)))
    op.add_column("component_sources", sa.Column("license_snapshot_url", sa.String(500)))
    op.add_column("component_sources", sa.Column("attribution_snapshot", sa.String(1000)))
    op.add_column("component_sources", sa.Column("parser_name", sa.String(80)))
    op.add_column("component_sources", sa.Column("parser_version", sa.String(40)))
    op.execute(
        "UPDATE component_sources SET original_url=canonical_url, "
        "imported_at=retrieved_at, parser_version=adapter_version"
    )
    op.drop_index("uq_component_sources_item", table_name="component_sources")
    op.create_index(
        "uq_component_sources_item",
        "component_sources",
        ["source_id", "source_item_id"],
        unique=True,
        postgresql_where=sa.text("source_item_id IS NOT NULL AND source_revision IS NULL"),
    )
    op.create_check_constraint(
        "ck_component_sources_revision_sha",
        "component_sources",
        "source_revision IS NULL OR source_revision ~ '^[0-9a-f]{40}$'",
    )
    op.create_index(
        "uq_component_sources_repository_entry",
        "component_sources",
        ["source_id", "source_revision", "source_file_path", "source_entry_name"],
        unique=True,
        postgresql_where=sa.text("source_revision IS NOT NULL AND source_file_path IS NOT NULL"),
    )

    op.add_column("import_jobs", sa.Column("repository_url", sa.String(500)))
    op.add_column("import_jobs", sa.Column("requested_revision", sa.String(100)))
    op.add_column("import_jobs", sa.Column("source_revision", sa.String(64)))
    op.add_column("import_jobs", sa.Column("source_file_path", sa.String(1000)))
    op.add_column("import_jobs", sa.Column("source_entry_name", sa.String(300)))
    op.add_column("import_jobs", sa.Column("parser_name", sa.String(80)))
    op.add_column("import_jobs", sa.Column("parse_status", sa.String(32)))
    op.add_column(
        "import_jobs",
        sa.Column(
            "warnings_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_check_constraint(
        "ck_import_jobs_parse_status",
        "import_jobs",
        "parse_status IS NULL OR parse_status IN "
        "('parsed','parsed_with_warnings','unsupported_document','source_drift',"
        "'invalid_metadata','license_missing','failed')",
    )
    op.create_check_constraint(
        "ck_import_jobs_revision_sha",
        "import_jobs",
        "source_revision IS NULL OR source_revision ~ '^[0-9a-f]{40}$'",
    )

    op.execute(
        """
        UPDATE sources SET
          display_name = CASE key WHEN 'alexgyver' THEN 'AlexGyver'
            WHEN 'arduino_tex' THEN 'Arduino-Tex' ELSE 'Portal-PK' END,
          status = CASE WHEN key='alexgyver' THEN 'disabled' ELSE 'inactive' END,
          permission_status = CASE WHEN key='alexgyver' THEN 'denied' ELSE 'unknown' END,
          disable_reason = CASE WHEN key='alexgyver' THEN 'owner_denied_usage' ELSE NULL END,
          is_enabled = false,
          allow_text_import = 'none', allow_facts_import = false,
          allow_media_import = false, allow_code_import = false, allow_attachment_import = false
        WHERE key IN ('arduino_tex','portal_pk','alexgyver')
        """
    )
    sources = (
        {
            "id": "00000000-0000-4000-9000-000000000004",
            "key": "seeed_wiki",
            "display_name": "Seeed Studio Wiki",
            "seed_url": "https://github.com/Seeed-Studio/wiki-documents",
            "source_type": "git_repository",
            "repository_url": "https://github.com/Seeed-Studio/wiki-documents",
            "owner": "Seeed-Studio",
            "name": "wiki-documents",
            "adapter": "seeed-wiki-git-v1",
            "license_name": "GNU General Public License v3.0 only",
            "license_spdx": "GPL-3.0-only",
            "license_url": "https://www.gnu.org/licenses/gpl-3.0.html",
            "content_policy": "facts_and_limited_adaptation",
            "attribution": "Seeed Studio Wiki, {original_url}, revision {source_revision}",
        },
        {
            "id": "00000000-0000-4000-9000-000000000005",
            "key": "kicad_symbols",
            "display_name": "Official KiCad Libraries",
            "seed_url": "https://gitlab.com/kicad/libraries/kicad-symbols",
            "source_type": "official_library",
            "repository_url": "https://gitlab.com/kicad/libraries/kicad-symbols",
            "owner": "kicad/libraries",
            "name": "kicad-symbols",
            "adapter": "kicad-symbols-v1",
            "license_name": "Creative Commons Attribution-ShareAlike 4.0 International",
            "license_spdx": "CC-BY-SA-4.0",
            "license_url": "https://gitlab.com/kicad/libraries/kicad-symbols/-/blob/master/LICENSE.md",
            "content_policy": "structured_metadata",
            "attribution": (
                "Official KiCad Libraries, {source_file_path}:{source_entry_name}, "
                "revision {source_revision}"
            ),
        },
    )
    for source in sources:
        op.execute(
            sa.text(
                "INSERT INTO sources "
                "(id,key,display_name,seed_url,allowed_host,adapter,adapter_version,policy,"
                "is_enabled,updated_at,source_type,status,repository_url,repository_owner,"
                "repository_name,default_revision_policy,license_name,license_spdx,license_url,"
                "attribution_template,permission_status,content_policy,allow_text_import,"
                "allow_facts_import,allow_media_import,allow_code_import,allow_attachment_import) "
                "VALUES (CAST(:id AS uuid),:key,:display_name,:seed_url,NULL,:adapter,'1.0.0',"
                "'licensed_content',true,now(),:source_type,'active',:repository_url,:owner,:name,"
                "'immutable_commit',:license_name,:license_spdx,:license_url,:attribution,"
                "'license_granted',:content_policy,'limited',true,false,false,false)"
            ).bindparams(**source)
        )


def downgrade() -> None:
    op.execute("DELETE FROM sources WHERE key IN ('seeed_wiki','kicad_symbols')")
    for constraint in ("ck_import_jobs_revision_sha", "ck_import_jobs_parse_status"):
        op.drop_constraint(constraint, "import_jobs", type_="check")
    for column in (
        "warnings_json",
        "parse_status",
        "parser_name",
        "source_entry_name",
        "source_file_path",
        "source_revision",
        "requested_revision",
        "repository_url",
    ):
        op.drop_column("import_jobs", column)
    op.drop_index("uq_component_sources_repository_entry", table_name="component_sources")
    op.drop_index("uq_component_sources_item", table_name="component_sources")
    op.create_index(
        "uq_component_sources_item",
        "component_sources",
        ["source_id", "source_item_id"],
        unique=True,
        postgresql_where=sa.text("source_item_id IS NOT NULL"),
    )
    op.drop_constraint("ck_component_sources_revision_sha", "component_sources", type_="check")
    for column in (
        "parser_version",
        "parser_name",
        "attribution_snapshot",
        "license_snapshot_url",
        "license_snapshot_spdx",
        "license_snapshot_name",
        "modifications_notice",
        "provenance_json",
        "imported_fields",
        "imported_at",
        "original_url",
        "source_entry_name",
        "source_file_path",
        "source_tag",
        "source_revision",
    ):
        op.drop_column("component_sources", column)
    op.drop_index("uq_sources_repository_url", table_name="sources")
    for constraint in (
        "ck_sources_repository_identity",
        "ck_sources_text_import",
        "ck_sources_permission",
        "ck_sources_revision_policy",
        "ck_sources_status",
        "ck_sources_type",
    ):
        op.drop_constraint(constraint, "sources", type_="check")
    for column in (
        "allow_attachment_import",
        "allow_code_import",
        "allow_media_import",
        "allow_facts_import",
        "allow_text_import",
        "disable_reason",
        "content_policy",
        "permission_status",
        "license_url",
        "license_spdx",
        "license_name",
        "default_revision_policy",
        "repository_name",
        "repository_owner",
        "repository_url",
        "status",
        "source_type",
        "display_name",
    ):
        op.drop_column("sources", column)
    op.alter_column("sources", "allowed_host", existing_type=sa.String(253), nullable=False)
    op.create_unique_constraint("sources_allowed_host_key", "sources", ["allowed_host"])
    op.execute(
        "UPDATE sources SET is_enabled=true WHERE key IN ('arduino_tex','portal_pk','alexgyver')"
    )
