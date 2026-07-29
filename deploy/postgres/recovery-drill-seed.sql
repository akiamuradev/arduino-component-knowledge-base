\set ON_ERROR_STOP on

INSERT INTO users (
    id, login, display_name, password_hash, status, created_at, updated_at
) VALUES (
    '10000000-0000-4000-8000-000000000001',
    'recovery-drill',
    'Recovery Drill',
    '$argon2id$v=19$m=65536,t=3,p=4$recovery$drill',
    'active',
    '2026-07-29T00:00:00Z',
    '2026-07-29T00:00:00Z'
);

INSERT INTO user_roles (
    id, user_id, role, granted_by, granted_at
) VALUES (
    '10000000-0000-4000-8000-000000000002',
    '10000000-0000-4000-8000-000000000001',
    'administrator',
    '10000000-0000-4000-8000-000000000001',
    '2026-07-29T00:00:00Z'
);

INSERT INTO components (
    id, slug, status, title, manufacturer, model,
    normalized_manufacturer, normalized_model, summary, description,
    difficulty, primary_category_id, manual_original, created_by, updated_by,
    created_at, updated_at, revision
) VALUES (
    '10000000-0000-4000-8000-000000000003',
    'recovery-drill-component',
    'draft',
    'Recovery drill component',
    'ACKB',
    'DRILL-1',
    'ackb',
    'drill 1',
    'Component preserved by the PostgreSQL recovery drill.',
    'This deterministic card proves that catalog data survives backup and restore.',
    'beginner',
    (SELECT id FROM categories WHERE key = 'integrated-circuits'),
    true,
    '10000000-0000-4000-8000-000000000001',
    '10000000-0000-4000-8000-000000000001',
    '2026-07-29T00:00:00Z',
    '2026-07-29T00:00:00Z',
    1
);

INSERT INTO component_revisions (
    id, component_id, revision, status, previous_status, action,
    change_summary, content_json, actor_id, created_at
) VALUES (
    '10000000-0000-4000-8000-000000000004',
    '10000000-0000-4000-8000-000000000003',
    1,
    'draft',
    NULL,
    'component.created',
    'Recovery drill card created',
    '{"source":"recovery-drill"}',
    '10000000-0000-4000-8000-000000000001',
    '2026-07-29T00:00:00Z'
);

INSERT INTO audit_events (
    id, occurred_at, actor_user_id, actor_type, action, object_type,
    object_id, request_id, outcome, details_safe_json
) VALUES (
    '10000000-0000-4000-8000-000000000005',
    '2026-07-29T00:00:00Z',
    '10000000-0000-4000-8000-000000000001',
    'user',
    'recovery.drill',
    'component',
    '10000000-0000-4000-8000-000000000003',
    'recovery-drill',
    'success',
    '{"source":"automated-recovery-drill"}'
);
