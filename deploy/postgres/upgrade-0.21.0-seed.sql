\set ON_ERROR_STOP on

-- Deterministic test-only snapshot of business data created by ACKB 0.21.0
-- (Alembic revision 20260721_16). Keep every INSERT compatible with that
-- revision so the release drill cannot silently start from a newer schema.

INSERT INTO users (
    id, login, display_name, password_hash, status, created_at, updated_at
) VALUES
(
    '21000000-0000-4000-8000-000000000001',
    'upgrade-administrator',
    'Upgrade Administrator',
    '$argon2id$v=19$m=65536,t=3,p=4$upgrade$administrator',
    'active',
    '2026-07-21T00:00:00Z',
    '2026-07-21T00:00:00Z'
),
(
    '21000000-0000-4000-8000-000000000002',
    'upgrade-student',
    'Upgrade Student',
    '$argon2id$v=19$m=65536,t=3,p=4$upgrade$student',
    'active',
    '2026-07-21T00:00:00Z',
    '2026-07-21T00:00:00Z'
);

INSERT INTO user_roles (
    user_id, role, granted_by, granted_at
) VALUES
(
    '21000000-0000-4000-8000-000000000001',
    'administrator',
    NULL,
    '2026-07-21T00:00:00Z'
),
(
    '21000000-0000-4000-8000-000000000002',
    'student',
    '21000000-0000-4000-8000-000000000001',
    '2026-07-21T00:00:00Z'
);

INSERT INTO components (
    id, slug, status, title, manufacturer, model,
    normalized_manufacturer, normalized_model, summary, description,
    difficulty, primary_category_id, manual_original, created_by, updated_by,
    created_at, updated_at, revision
) VALUES (
    '21000000-0000-4000-8000-000000000003',
    'upgrade-preserved-component',
    'draft',
    'Upgrade preserved component',
    'ACKB',
    'UPGRADE-021',
    'ackb',
    'upgrade021',
    'A component created before the ACKB 1.0.0 upgrade.',
    'This deterministic card must survive migration and rollback without content loss.',
    'beginner',
    (SELECT id FROM categories WHERE key = 'integrated-circuits'),
    true,
    '21000000-0000-4000-8000-000000000001',
    '21000000-0000-4000-8000-000000000001',
    '2026-07-21T00:00:00Z',
    '2026-07-21T00:00:00Z',
    1
);

INSERT INTO component_revisions (
    id, component_id, revision, status, content_json, actor_id, created_at
) VALUES (
    '21000000-0000-4000-8000-000000000004',
    '21000000-0000-4000-8000-000000000003',
    1,
    'draft',
    '{"source":"ackb-0.21.0","title":"Upgrade preserved component"}',
    '21000000-0000-4000-8000-000000000001',
    '2026-07-21T00:00:00Z'
);

INSERT INTO import_jobs (
    id, source_id, submitted_url, canonical_url, status, requested_by,
    idempotency_key, attempts, max_attempts, parser_version, draft_component_id,
    error_code, created_at, started_at, next_retry_at, finished_at, updated_at,
    repository_url, requested_revision, source_revision, source_file_path,
    source_entry_name, parser_name, parse_status, warnings_json, heartbeat_at,
    metrics_json
) VALUES (
    '21000000-0000-4000-8000-000000000005',
    (SELECT id FROM sources WHERE key = 'seeed_wiki'),
    'https://github.com/Seeed-Studio/wiki-documents',
    'https://github.com/Seeed-Studio/wiki-documents',
    'succeeded',
    '21000000-0000-4000-8000-000000000001',
    'upgrade-preserved-import',
    1,
    4,
    '1.1.0',
    '21000000-0000-4000-8000-000000000003',
    NULL,
    '2026-07-21T00:00:00Z',
    '2026-07-21T00:00:00Z',
    NULL,
    '2026-07-21T00:01:00Z',
    '2026-07-21T00:01:00Z',
    'https://github.com/Seeed-Studio/wiki-documents',
    'master',
    '0123456789abcdef0123456789abcdef01234567',
    'docs/Sensor/Upgrade.md',
    NULL,
    'seeed-wiki-git-v1',
    'parsed',
    '[]',
    '2026-07-21T00:00:30Z',
    '{"items":1}'
);

INSERT INTO audit_events (
    id, occurred_at, actor_user_id, actor_type, action, object_type,
    object_id, request_id, outcome, details_safe_json
) VALUES (
    '21000000-0000-4000-8000-000000000006',
    '2026-07-21T00:01:00Z',
    '21000000-0000-4000-8000-000000000001',
    'user',
    'upgrade.fixture_created',
    'component',
    '21000000-0000-4000-8000-000000000003',
    'upgrade-0.21.0',
    'success',
    '{"source":"release-upgrade-drill"}'
);
