#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TEMPORARY_DIR="$(mktemp -d)"
readonly ACKB_SECURITY_PROJECT="ackb-security-${RANDOM}-${RANDOM}"
readonly ENVIRONMENT_FILE="${TEMPORARY_DIR}/environment"
readonly -a COMPOSE_ARGUMENTS=(
  --project-name "$ACKB_SECURITY_PROJECT"
  --env-file "$ENVIRONMENT_FILE"
  --file "$ROOT_DIR/compose.yaml"
  --file "$ROOT_DIR/compose.production.yaml"
)

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

docker compose "${COMPOSE_ARGUMENTS[@]}" up --detach --wait postgres redis minio
docker compose "${COMPOSE_ARGUMENTS[@]}" run --rm --no-deps migrate
docker compose "${COMPOSE_ARGUMENTS[@]}" run --rm --no-deps database-permissions
docker compose "${COMPOSE_ARGUMENTS[@]}" run --rm --no-deps minio-identity-init
docker compose "${COMPOSE_ARGUMENTS[@]}" run --rm --no-deps media-init

database_contract="$(docker compose "${COMPOSE_ARGUMENTS[@]}" exec --no-TTY postgres sh -c '
  PGPASSWORD="$POSTGRES_PASSWORD" psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --tuples-only --no-align --command \
    "SELECT CASE WHEN NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls THEN '\''pass'\'' ELSE '\''fail'\'' END FROM pg_roles WHERE rolname = '\''ackb_runtime'\'';
     SELECT CASE WHEN NOT has_schema_privilege('\''ackb_runtime'\'', '\''public'\'', '\''CREATE'\'') THEN '\''pass'\'' ELSE '\''fail'\'' END;
     SELECT CASE WHEN has_table_privilege('\''ackb_runtime'\'', '\''users'\'', '\''SELECT,INSERT,UPDATE,DELETE'\'') THEN '\''pass'\'' ELSE '\''fail'\'' END;
     SELECT CASE WHEN NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls THEN '\''pass'\'' ELSE '\''fail'\'' END FROM pg_roles WHERE rolname = '\''ackb_backup'\'';
     SELECT CASE WHEN has_table_privilege('\''ackb_backup'\'', '\''users'\'', '\''SELECT'\'') AND NOT has_table_privilege('\''ackb_backup'\'', '\''users'\'', '\''INSERT,UPDATE,DELETE'\'') THEN '\''pass'\'' ELSE '\''fail'\'' END;
     SELECT CASE WHEN NOT has_schema_privilege('\''ackb_backup'\'', '\''public'\'', '\''CREATE'\'') THEN '\''pass'\'' ELSE '\''fail'\'' END;"
')"
if [[ "$database_contract" != $'pass\npass\npass\npass\npass\npass' ]]; then
  printf 'ERROR: production PostgreSQL runtime grant contract failed: %q\n' \
    "$database_contract" >&2
  exit 1
fi

docker compose "${COMPOSE_ARGUMENTS[@]}" exec --no-TTY redis sh -c '
  if redis-cli ping 2>/dev/null | grep -q -F PONG; then
    exit 1
  fi
  REDISCLI_AUTH="$ACKB_REDIS_PASSWORD" redis-cli ping | grep -q -F PONG
'

docker compose "${COMPOSE_ARGUMENTS[@]}" run --rm --no-deps \
  --entrypoint /bin/sh minio-identity-init -c '
    mc alias set ackb-runtime https://minio:9000 "$ACKB_MINIO_ACCESS_KEY" "$ACKB_MINIO_SECRET_KEY" >/dev/null
    mc ls ackb-runtime/ackb-media-quarantine >/dev/null
    mc ls ackb-runtime/ackb-media-variants >/dev/null
    if mc admin info ackb-runtime >/dev/null 2>&1; then
      exit 1
    fi
  '

printf 'Production database, Redis and MinIO identity smoke test passed.\n'
