"""Static contracts for the PostgreSQL recovery workflow."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_backup_is_private_validated_and_has_a_data_manifest() -> None:
    backup = (ROOT / "scripts" / "database_backup.sh").read_text(encoding="utf-8")
    manifest = (ROOT / "deploy" / "postgres" / "backup-manifest.sql").read_text(encoding="utf-8")
    assert "umask" not in backup  # Files are explicitly created and retained with mode 0600.
    assert "chmod 600" in backup
    assert "--format=custom" in backup
    assert "--serializable-deferrable" in backup
    assert "--entrypoint pg_restore" in backup
    for protected_data in (
        "'users'",
        "'roles'",
        "'components'",
        "'component_revisions'",
        "'component_correction_proposals'",
        "'audit_events'",
    ):
        assert protected_data in manifest
    assert "password_hash" not in manifest
    assert "login" not in manifest
    assert "message" not in manifest


def test_restore_refuses_a_production_target_and_verifies_critical_data() -> None:
    restore = (ROOT / "scripts" / "database_restore.sh").read_text(encoding="utf-8")
    assert "^ackb_restore_" in restore
    assert "checksum mismatch" in restore
    assert "--exit-on-error" in restore
    assert "cmp --silent" in restore
    assert "database-restore-migrate" in restore
    assert "database-permissions" in restore
    assert "revision/correction history" in restore
    assert "production database was not changed" in restore


def test_recovery_drill_covers_clean_install_previous_head_and_restore() -> None:
    drill = (ROOT / "scripts" / "database_restore_smoke.sh").read_text(encoding="utf-8")
    assert "20260721_16" in drill
    assert "20260729_28 (head)" in drill
    assert "database_backup.sh" in drill
    assert "database_restore.sh" in drill
    assert "recovery-drill-seed.sql" in drill
    assert "upgrade-0.21.0-seed.sql" in drill
    assert "upgrade-drill-signature.sql" in drill
    assert "alembic downgrade 20260721_16" in drill
    assert "--entrypoint pg_restore" in drill
    assert "sha256sum --check" in drill
