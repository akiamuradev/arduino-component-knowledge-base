#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="${1:-}"
readonly DUMP_FILE="${2:-}"
readonly TARGET_DATABASE="${3:-}"
readonly PROJECT_NAME="${4:-arduino-component-kb}"
readonly MANIFEST_FILE="${DUMP_FILE}.manifest.json"
readonly CHECKSUM_FILE="${DUMP_FILE}.sha256"
TARGET_CREATED="false"
RESTORE_SUCCEEDED="false"
TARGET_MANIFEST=""
readonly -a COMPOSE_ARGUMENTS=(
  --project-name "$PROJECT_NAME"
  --env-file "$ENV_FILE"
  --file "$ROOT_DIR/compose.yaml"
  --file "$ROOT_DIR/compose.production.yaml"
  --profile restore
)

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

compose_restore() {
  ACKB_RESTORE_DATABASE="$TARGET_DATABASE" docker compose "${COMPOSE_ARGUMENTS[@]}" "$@"
}

drop_target() {
  compose_restore run --quiet-pull --rm --no-deps --no-TTY \
    --env PGDATABASE=postgres \
    --entrypoint psql database-restore-tools \
    --set ON_ERROR_STOP=1 \
    --command "DROP DATABASE IF EXISTS \"$TARGET_DATABASE\" WITH (FORCE)" >/dev/null
}

cleanup() {
  [[ -z "$TARGET_MANIFEST" ]] || rm -f -- "$TARGET_MANIFEST"
  if [[ "$TARGET_CREATED" == "true" && "$RESTORE_SUCCEEDED" != "true" ]]; then
    drop_target || true
  fi
}
trap cleanup EXIT

for command in awk cmp docker mktemp sha256sum stat; do
  command -v "$command" >/dev/null 2>&1 || fail "required command '$command' is unavailable"
done
[[ -r "$ENV_FILE" ]] || fail "production environment file is not readable: $ENV_FILE"
[[ -f "$DUMP_FILE" && -r "$DUMP_FILE" ]] || fail "backup dump is not readable: $DUMP_FILE"
[[ -f "$MANIFEST_FILE" && -r "$MANIFEST_FILE" ]] \
  || fail "backup manifest is not readable: $MANIFEST_FILE"
[[ -f "$CHECKSUM_FILE" && -r "$CHECKSUM_FILE" ]] \
  || fail "backup checksum is not readable: $CHECKSUM_FILE"
[[ "$TARGET_DATABASE" =~ ^ackb_restore_[a-z0-9_]{1,47}$ ]] \
  || fail "target database must match ackb_restore_[a-z0-9_]+"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail "project name contains unsafe characters"

for protected_file in "$DUMP_FILE" "$MANIFEST_FILE" "$CHECKSUM_FILE"; do
  mode="$(stat -c '%a' "$protected_file")"
  (( (8#$mode & 8#077) == 0 )) || fail "$protected_file must not be accessible by group or others"
done

expected_checksum="$(awk 'NR == 1 {print $1}' "$CHECKSUM_FILE")"
[[ "$expected_checksum" =~ ^[0-9a-f]{64}$ ]] || fail "backup checksum file is invalid"
actual_checksum="$(sha256sum "$DUMP_FILE" | awk '{print $1}')"
[[ "$actual_checksum" == "$expected_checksum" ]] || fail "backup checksum mismatch"
compose_restore run --quiet-pull --rm --no-deps --no-TTY \
  --entrypoint pg_restore database-restore-tools --list <"$DUMP_FILE" >/dev/null

drop_target
compose_restore run --quiet-pull --rm --no-deps --no-TTY \
  --env PGDATABASE=postgres \
  --entrypoint psql database-restore-tools \
  --set ON_ERROR_STOP=1 \
  --command "CREATE DATABASE \"$TARGET_DATABASE\" TEMPLATE template0 ENCODING 'UTF8'" >/dev/null
TARGET_CREATED="true"

compose_restore run --quiet-pull --rm --no-deps --no-TTY \
  --env PGDATABASE="$TARGET_DATABASE" \
  --entrypoint pg_restore database-restore-tools \
  --exit-on-error \
  --no-owner \
  --no-acl \
  --dbname "$TARGET_DATABASE" <"$DUMP_FILE"

TARGET_MANIFEST="$(mktemp)"
chmod 600 "$TARGET_MANIFEST"
compose_restore run --quiet-pull --rm --no-deps --no-TTY \
  --env PGDATABASE="$TARGET_DATABASE" \
  --entrypoint psql database-restore-tools \
  --set ON_ERROR_STOP=1 \
  --file /etc/ackb/backup-manifest.sql >"$TARGET_MANIFEST"
cmp --silent "$MANIFEST_FILE" "$TARGET_MANIFEST" \
  || fail "restored users, roles, components, revisions or audit history differ from the backup"

compose_restore run --quiet-pull --rm --no-deps --no-TTY database-restore-migrate
compose_restore run --quiet-pull --rm --no-deps --no-TTY \
  --env PGDATABASE="$TARGET_DATABASE" \
  --entrypoint psql database-restore-tools \
  --set ON_ERROR_STOP=1 \
  --file /etc/ackb/backup-manifest.sql >"$TARGET_MANIFEST"
cmp --silent "$MANIFEST_FILE" "$TARGET_MANIFEST" \
  || fail "migration changed the restored schema revision or critical data"
compose_restore run --quiet-pull --rm --no-deps --no-TTY \
  --env PGDATABASE="$TARGET_DATABASE" database-permissions
RESTORE_SUCCEEDED="true"

printf 'PostgreSQL restore verified in isolated database: %s\n' "$TARGET_DATABASE"
printf 'Critical users, roles, components, revision history and audit events match the backup.\n'
printf 'The production database was not changed; inspect the target before any manual cutover.\n'
