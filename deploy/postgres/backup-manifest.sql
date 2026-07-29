\pset tuples_only on
\pset format unaligned

SELECT json_build_object(
    'format_version', 1,
    'alembic_revision', (SELECT version_num FROM alembic_version),
    'users', json_build_object(
        'count', (SELECT count(*) FROM users),
        'fingerprint', (
            SELECT md5(coalesce(string_agg(id::text, ',' ORDER BY id::text), '')) FROM users
        )
    ),
    'roles', json_build_object(
        'count', (SELECT count(*) FROM user_roles),
        'fingerprint', (
            SELECT md5(coalesce(string_agg(
                concat_ws(':', id, user_id, role, granted_at, expires_at, revoked_at),
                ',' ORDER BY id::text
            ), ''))
            FROM user_roles
        )
    ),
    'components', json_build_object(
        'count', (SELECT count(*) FROM components),
        'fingerprint', (
            SELECT md5(coalesce(string_agg(
                concat_ws(':', id, slug, status, revision), ',' ORDER BY id::text
            ), ''))
            FROM components
        )
    ),
    'component_revisions', json_build_object(
        'count', (SELECT count(*) FROM component_revisions),
        'fingerprint', (
            SELECT md5(coalesce(string_agg(
                concat_ws(':', id, component_id, revision, status, action),
                ',' ORDER BY id::text
            ), ''))
            FROM component_revisions
        )
    ),
    'component_correction_proposals', json_build_object(
        'count', (SELECT count(*) FROM component_correction_proposals),
        'fingerprint', (
            SELECT md5(coalesce(string_agg(
                concat_ws(
                    ':', id, component_id, author_id, status, created_at,
                    resolved_by, resolved_at
                ),
                ',' ORDER BY id::text
            ), ''))
            FROM component_correction_proposals
        )
    ),
    'audit_events', json_build_object(
        'count', (SELECT count(*) FROM audit_events),
        'fingerprint', (
            SELECT md5(coalesce(string_agg(id::text, ',' ORDER BY id::text), ''))
            FROM audit_events
        )
    )
)::text;
