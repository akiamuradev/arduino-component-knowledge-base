#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly TEMPORARY_DIR="$(mktemp -d)"
readonly ACKB_CLEAN_PROJECT="ackb-clean-${RANDOM}-${RANDOM}"
readonly ENVIRONMENT_FILE="${TEMPORARY_DIR}/environment"
readonly -a COMPOSE_ARGUMENTS=(
  --project-name "$ACKB_CLEAN_PROJECT"
  --env-file "$ENVIRONMENT_FILE"
  --file "$ROOT_DIR/compose.yaml"
)

cleanup() {
  local exit_status=$?
  trap - EXIT
  if [[ "$exit_status" -ne 0 ]]; then
    docker compose "${COMPOSE_ARGUMENTS[@]}" ps >&2 || true
    docker compose "${COMPOSE_ARGUMENTS[@]}" logs \
      --tail=100 postgres redis minio migrate media-init backend frontend reverse-proxy >&2 || true
  fi
  docker compose "${COMPOSE_ARGUMENTS[@]}" down \
    --volumes --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "$TEMPORARY_DIR"
  exit "$exit_status"
}
trap cleanup EXIT

sed \
  -e 's|replace-with-local-postgres-password|clean-postgres-password-000000000000|' \
  -e 's|replace-with-local-password|clean-postgres-password-000000000000|' \
  -e 's|replace-with-local-minio-user|clean-minio-user|' \
  -e 's|replace-with-local-minio-password|clean-minio-password-0000000000000000|' \
  -e 's|replace-with-local-access-key|clean-minio-user|' \
  -e 's|replace-with-local-secret-key|clean-minio-password-0000000000000000|' \
  -e 's|replace-with-at-least-32-random-characters|clean-auth-pepper-00000000000000000000|' \
  -e 's|^ACKB_HTTP_PORT=.*|ACKB_HTTP_PORT=0|' \
  "$ROOT_DIR/.env.example" >"$ENVIRONMENT_FILE"
chmod 600 "$ENVIRONMENT_FILE"

up_arguments=(--no-build --detach --wait)
if [[ "${ACKB_CLEAN_STACK_SKIP_BUILD:-false}" != "true" ]]; then
  python3 "$ROOT_DIR/scripts/build_images.py" --env-file "$ENVIRONMENT_FILE" --file "$ROOT_DIR/compose.yaml"
fi
docker compose "${COMPOSE_ARGUMENTS[@]}" up "${up_arguments[@]}"

database_contract="$(docker compose "${COMPOSE_ARGUMENTS[@]}" exec --no-TTY postgres sh -c '
  PGPASSWORD="$POSTGRES_PASSWORD" psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --tuples-only --no-align --set ON_ERROR_STOP=1 --command \
    "SELECT
       (SELECT count(*) FROM users),
       (SELECT count(*) FROM components),
       (SELECT count(*) FROM import_jobs),
       (SELECT count(*) FROM component_correction_proposals),
       (SELECT version_num FROM alembic_version);"
')"
if [[ "$database_contract" != "0|0|0|0|20260911_31" ]]; then
  printf 'ERROR: clean database contract failed: %q\n' "$database_contract" >&2
  exit 1
fi

published_address="$(
  docker compose "${COMPOSE_ARGUMENTS[@]}" port reverse-proxy 8080 | tail -n 1
)"
published_port="${published_address##*:}"
if [[ ! "$published_port" =~ ^[0-9]+$ ]]; then
  printf 'ERROR: could not determine clean stack HTTP port: %q\n' "$published_address" >&2
  exit 1
fi
base_url="http://127.0.0.1:${published_port}"

health_body="$(curl --fail --silent --show-error --max-time 10 "${base_url}/health")"
ready_body="$(curl --fail --silent --show-error --max-time 10 "${base_url}/ready")"
frontend_body="$(curl --fail --silent --show-error --max-time 10 "${base_url}/")"
build_body="$(curl --fail --silent --show-error --max-time 10 "${base_url}/build-info.json")"
python3 - "$health_body" "$build_body" "$(git -C "$ROOT_DIR" rev-parse HEAD)" "$ROOT_DIR/pyproject.toml" <<'PY'
import json
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

health, build = map(json.loads, sys.argv[1:3])
version = tomllib.loads(Path(sys.argv[4]).read_text())["project"]["version"]
assert health["version"] == build["version"] == version
assert build["commitSha"] == sys.argv[3]
assert build["buildDate"].endswith("Z")
built_at = datetime.fromisoformat(build["buildDate"].replace("Z", "+00:00"))
assert 0 <= (datetime.now(timezone.utc) - built_at).total_seconds() < 86400
print("HTTP build identity matches project version, checked-out SHA and recent UTC build time.")
PY

grep -q -F '"status":"ok"' <<<"$health_body"
grep -q -F '"status":"ready"' <<<"$ready_body"
grep -q -F '<div id="root">' <<<"$frontend_body"

printf 'Clean database application startup and HTTP smoke test passed.\n'
