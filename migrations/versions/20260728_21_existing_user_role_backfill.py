"""Backfill a safe role for existing users without an active baseline grant.

Revision ID: 20260728_21
Revises: 20260728_20
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260728_21"
down_revision: str | None = "20260728_20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the inventory stable while the data migration identifies users without
    # a non-temporary baseline grant. Normal deployments stop application writes while
    # the one-shot Compose migration service is running.
    op.execute("LOCK TABLE users IN SHARE ROW EXCLUSIVE MODE")
    op.execute("LOCK TABLE user_roles IN SHARE ROW EXCLUSIVE MODE")
    op.execute(
        """
        INSERT INTO user_roles (
            id,
            user_id,
            role,
            granted_by,
            granted_at,
            expires_at,
            revoked_at
        )
        SELECT
            md5('ackb-1.0.0-safe-student:' || users.id::text)::uuid,
            users.id,
            'student',
            NULL,
            CURRENT_TIMESTAMP,
            NULL,
            NULL
        FROM users
        WHERE NOT EXISTS (
            SELECT 1
            FROM user_roles
            WHERE user_roles.user_id = users.id
              AND user_roles.revoked_at IS NULL
              AND user_roles.role IN ('student', 'teacher', 'administrator')
        )
        """
    )
    op.execute(
        """
        DO $ackb_role_backfill$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM users
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM user_roles
                    WHERE user_roles.user_id = users.id
                      AND user_roles.revoked_at IS NULL
                      AND user_roles.role IN ('student', 'teacher', 'administrator')
                )
            ) THEN
                RAISE EXCEPTION
                    USING
                        ERRCODE = 'check_violation',
                        MESSAGE = 'ACKB role backfill left a user without an active baseline role';
            END IF;
        END
        $ackb_role_backfill$
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM user_roles
        WHERE id = md5('ackb-1.0.0-safe-student:' || user_id::text)::uuid
          AND role = 'student'
          AND granted_by IS NULL
        """
    )
