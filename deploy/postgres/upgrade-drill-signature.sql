\set ON_ERROR_STOP on
\pset tuples_only on
\pset format unaligned

-- Use only columns shared by 0.21.0 and 1.0.0. Identical output before and
-- after migration proves that critical identities and business history stayed
-- byte-for-byte stable while allowing the schema revision itself to change.
SELECT json_build_object(
    'users', (
        SELECT md5(string_agg(
            concat_ws(':', id, login, display_name, status, created_at, updated_at),
            ',' ORDER BY id::text
        ))
        FROM users
        WHERE id IN (
            '21000000-0000-4000-8000-000000000001',
            '21000000-0000-4000-8000-000000000002'
        )
    ),
    'roles', (
        SELECT md5(string_agg(
            concat_ws(':', user_id, role, granted_by, granted_at),
            ',' ORDER BY user_id::text, role
        ))
        FROM user_roles
        WHERE user_id IN (
            '21000000-0000-4000-8000-000000000001',
            '21000000-0000-4000-8000-000000000002'
        )
    ),
    'components', (
        SELECT md5(string_agg(
            concat_ws(
                ':', id, slug, status, title, manufacturer, model, summary,
                description, difficulty, primary_category_id, manual_original,
                created_by, updated_by, created_at, updated_at, revision
            ),
            ',' ORDER BY id::text
        ))
        FROM components
        WHERE id = '21000000-0000-4000-8000-000000000003'
    ),
    'component_revisions', (
        SELECT md5(string_agg(
            concat_ws(
                ':', id, component_id, revision, status, content_json::text,
                actor_id, created_at
            ),
            ',' ORDER BY id::text
        ))
        FROM component_revisions
        WHERE id = '21000000-0000-4000-8000-000000000004'
    ),
    'import_jobs', (
        SELECT md5(string_agg(
            concat_ws(
                ':', id, source_id, status, requested_by, idempotency_key,
                attempts, max_attempts, parser_version, draft_component_id,
                source_revision, source_file_path, parser_name, parse_status,
                warnings_json::text, metrics_json::text
            ),
            ',' ORDER BY id::text
        ))
        FROM import_jobs
        WHERE id = '21000000-0000-4000-8000-000000000005'
    ),
    'audit_events', (
        SELECT md5(string_agg(
            concat_ws(
                ':', id, occurred_at, actor_user_id, actor_type, action,
                object_type, object_id, request_id, outcome, details_safe_json::text
            ),
            ',' ORDER BY id::text
        ))
        FROM audit_events
        WHERE id = '21000000-0000-4000-8000-000000000006'
    )
)::text;
