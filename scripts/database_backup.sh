#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="${1:-${ROOT_DIR}/.env.production}"
readonly OUTPUT_DIR="${2:-${ROOT_DIR}/backups}"
readonly PROJECT_NAME="${3:-arduino-component-kb}"
readonly TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
readonly BACKUP_NAME="ackb-postgresql-${TIMESTAMP}.dump"
readonly FINAL_DUMP="${OUTPUT_DIR}/${BACKUP_NAME}"
readonly FINAL_MANIFEST="${FINAL_DUMP}.manifest.json"
readonly FINAL_CHECKSUM="${FINAL_DUMP}.sha256"
TEMP_DUMP=""
TEMP_MANIFEST=""
TEMP_CHECKSUM=""
readonly -a COMPOSE_ARGUMENTS=(
  --project-name "$PROJECT_NAME"
  --env-file "$ENV_FILE"
  --file "$ROOT_DIR/compose.yaml"
  --file "$ROOT_DIR/compose.production.yaml"
  --profile maintenance
)

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  [[ -z "$TEMP_DUMP" ]] || rm -f -- "$TEMP_DUMP"
  [[ -z "$TEMP_MANIFEST" ]] || rm -f -- "$TEMP_MANIFEST"
  [[ -z "$TEMP_CHECKSUM" ]] || rm -f -- "$TEMP_CHECKSUM"
}
trap cleanup EXIT

for command in cut date docker grep mkdir mktemp mv sha256sum stat; do
  command -v "$command" >/dev/null 2>&1 || fail "required command '$command' is unavailable"
done
[[ -r "$ENV_FILE" ]] || fail "production environment file is not readable: $ENV_FILE"
[[ "$PROJECT_NAME" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || fail "project name contains unsafe characters"

mkdir -p -- "$OUTPUT_DIR"
[[ -d "$OUTPUT_DIR" && -w "$OUTPUT_DIR" ]] || fail "backup directory is not writable: $OUTPUT_DIR"
[[ ! -e "$FINAL_DUMP" && ! -e "$FINAL_MANIFEST" && ! -e "$FINAL_CHECKSUM" ]] \
  || fail "backup with timestamp $TIMESTAMP already exists"

TEMP_DUMP="$(mktemp "${OUTPUT_DIR}/.ackb-dump.XXXXXX")"
TEMP_MANIFEST="$(mktemp "${OUTPUT_DIR}/.ackb-manifest.XXXXXX")"
TEMP_CHECKSUM="$(mktemp "${OUTPUT_DIR}/.ackb-checksum.XXXXXX")"
chmod 600 "$TEMP_DUMP" "$TEMP_MANIFEST" "$TEMP_CHECKSUM"

printf 'Creating PostgreSQL backup in a write-free maintenance window...\n'
docker compose "${COMPOSE_ARGUMENTS[@]}" run --quiet-pull --rm --no-deps --no-TTY \
  database-backup \
  --format=custom \
  --compress=zstd:9 \
  --no-owner \
  --no-acl \
  --serializable-deferrable \
  >"$TEMP_DUMP"

[[ -s "$TEMP_DUMP" ]] || fail "pg_dump produced an empty backup"
docker compose "${COMPOSE_ARGUMENTS[@]}" run --quiet-pull --rm --no-deps --no-TTY \
  --entrypoint pg_restore database-backup --list <"$TEMP_DUMP" >/dev/null

docker compose "${COMPOSE_ARGUMENTS[@]}" run --quiet-pull --rm --no-deps --no-TTY \
  --entrypoint psql database-backup \
  --set ON_ERROR_STOP=1 \
  --file /etc/ackb/backup-manifest.sql >"$TEMP_MANIFEST"
[[ "$(stat -c '%s' "$TEMP_MANIFEST")" -le 16384 ]] \
  || fail "backup manifest exceeded the safety limit"
grep -Eq '"format_version"[[:space:]]*:[[:space:]]*1' "$TEMP_MANIFEST" \
  || fail "backup manifest is invalid"

printf '%s  %s\n' "$(sha256sum "$TEMP_DUMP" | cut -d' ' -f1)" "$BACKUP_NAME" \
  >"$TEMP_CHECKSUM"
mv -- "$TEMP_DUMP" "$FINAL_DUMP"
TEMP_DUMP=""
mv -- "$TEMP_MANIFEST" "$FINAL_MANIFEST"
TEMP_MANIFEST=""
mv -- "$TEMP_CHECKSUM" "$FINAL_CHECKSUM"
TEMP_CHECKSUM=""
chmod 600 "$FINAL_DUMP" "$FINAL_MANIFEST" "$FINAL_CHECKSUM"

printf 'PostgreSQL backup created: %s\n' "$FINAL_DUMP"
printf 'Keep the dump, manifest and checksum together in encrypted off-host storage.\n'
