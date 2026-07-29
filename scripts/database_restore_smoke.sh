#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TEMPORARY_DIR="$(mktemp -d)"
readonly ACKB_RECOVERY_PROJECT="ackb-recovery-${RANDOM}-${RANDOM}"
readonly ENVIRONMENT_FILE="${TEMPORARY_DIR}/environment"
readonly RESTORE_DATABASE="ackb_restore_drill"
readonly UPGRADE_DATABASE="ackb_restore_upgrade"
readonly -a COMPOSE_ARGUMENTS=(
  --project-name "$ACKB_RECOVERY_PROJECT"
  --env-file "$ENVIRONMENT_FILE"
  --file "$ROOT_DIR/compose.yaml"
  --file "$ROOT_DIR/compose.production.yaml"
  --profile restore
)

database_admin() {
  local database="$1"
  shift
  ACKB_RESTORE_DATABASE="$database" docker compose "${COMPOSE_ARGUMENTS[@]}" run \
    --quiet-pull --rm --no-deps --no-TTY \
    --env PGDATABASE=postgres \
    --entrypoint psql database-restore-tools \
    --set ON_ERROR_STOP=1 "$@"
}

cleanup() {
  docker compose "${COMPOSE_ARGUMENTS[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "$TEMPORARY_DIR"
}
trap cleanup EXIT

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=kb.test.internal' \
  -addext 'subjectAltName=DNS:kb.test.internal,DNS:minio' \
  -keyout "$TEMPORARY_DIR/tls.key" \
  -out "$TEMPORARY_DIR/tls.crt" >/dev/null 2>&1
chmod 600 "$TEMPORARY_DIR/tls.key"

sed \
  -e 's|replace-with-production-postgres-password|ci-postgres-owner-password-000000000|' \
  -e 's|replace-with-production-runtime-postgres-password|ci-postgres-runtime-password-0000000|' \
  -e 's|replace-with-production-backup-postgres-password|ci-postgres-backup-password-00000000|' \
  -e 's|replace-with-production-minio-user|ci-minio-user|' \
  -e 's|replace-with-production-minio-password|ci-minio-root-password-0000000000000|' \
  -e 's|replace-with-production-minio-runtime-secret|ci-minio-runtime-password-000000000|' \
  -e 's|replace-with-production-redis-password|ci-redis-password-00000000000000000|' \
  -e 's|replace-with-at-least-32-random-characters|ci-only-pepper-value-00000000000000|' \
  -e 's|replace-with-internal-dns-name|kb.test.internal|' \
  -e 's|replace-with-static-ip|127.0.0.1|' \
  -e "s|replace-with-absolute-edge-certificate-path|$TEMPORARY_DIR/tls.crt|" \
  -e "s|replace-with-absolute-edge-private-key-path|$TEMPORARY_DIR/tls.key|" \
  -e "s|replace-with-absolute-minio-certificate-path|$TEMPORARY_DIR/tls.crt|" \
  -e "s|replace-with-absolute-minio-private-key-path|$TEMPORARY_DIR/tls.key|" \
  -e "s|replace-with-absolute-ca-bundle-path|$TEMPORARY_DIR/tls.crt|" \
  -e 's|replace-with-deployed-commit-sha|0123456789abcdef0123456789abcdef01234567|' \
  -e 's|replace-with-ISO-8601-build-date|2026-07-29T00:00:00Z|' \
  "$ROOT_DIR/.env.production.example" >"$ENVIRONMENT_FILE"
chmod 600 "$ENVIRONMENT_FILE"
mkdir -m 700 "$TEMPORARY_DIR/backups"

docker compose "${COMPOSE_ARGUMENTS[@]}" up --detach --wait postgres

# A brand-new database must migrate through the complete chain to the single head.
docker compose "${COMPOSE_ARGUMENTS[@]}" run --quiet-pull --rm --no-deps migrate
docker compose "${COMPOSE_ARGUMENTS[@]}" run --quiet-pull --rm --no-deps database-permissions
ACKB_RESTORE_DATABASE=ackb docker compose "${COMPOSE_ARGUMENTS[@]}" run \
  --quiet-pull --rm --no-deps --no-TTY \
  --env PGDATABASE=ackb \
  --entrypoint psql database-restore-tools \
  --set ON_ERROR_STOP=1 <"$ROOT_DIR/deploy/postgres/recovery-drill-seed.sql"

"$ROOT_DIR/scripts/database_backup.sh" \
  "$ENVIRONMENT_FILE" "$TEMPORARY_DIR/backups" "$ACKB_RECOVERY_PROJECT"
dump_file="$(find "$TEMPORARY_DIR/backups" -maxdepth 1 -name '*.dump' -type f -print -quit)"
[[ -n "$dump_file" ]]
"$ROOT_DIR/scripts/database_restore.sh" \
  "$ENVIRONMENT_FILE" "$dump_file" "$RESTORE_DATABASE" "$ACKB_RECOVERY_PROJECT"

# Simulate the supported update path from the previous project schema to current head.
database_admin "$UPGRADE_DATABASE" \
  --command "DROP DATABASE IF EXISTS \"$UPGRADE_DATABASE\" WITH (FORCE)"
database_admin "$UPGRADE_DATABASE" \
  --command "CREATE DATABASE \"$UPGRADE_DATABASE\" TEMPLATE template0 ENCODING 'UTF8'"
ACKB_RESTORE_DATABASE="$UPGRADE_DATABASE" docker compose "${COMPOSE_ARGUMENTS[@]}" run \
  --quiet-pull --rm --no-deps database-restore-migrate alembic upgrade 20260729_25
ACKB_RESTORE_DATABASE="$UPGRADE_DATABASE" docker compose "${COMPOSE_ARGUMENTS[@]}" run \
  --quiet-pull --rm --no-deps database-restore-migrate
current_revision="$(
  ACKB_RESTORE_DATABASE="$UPGRADE_DATABASE" docker compose "${COMPOSE_ARGUMENTS[@]}" run \
    --quiet-pull --rm --no-deps database-restore-migrate alembic current
)"
grep -q '20260729_27 (head)' <<<"$current_revision"

database_admin "$RESTORE_DATABASE" \
  --command "DROP DATABASE \"$RESTORE_DATABASE\" WITH (FORCE)"
database_admin "$UPGRADE_DATABASE" \
  --command "DROP DATABASE \"$UPGRADE_DATABASE\" WITH (FORCE)"

printf 'Clean migration, previous-version upgrade and PostgreSQL restore drill passed.\n'
