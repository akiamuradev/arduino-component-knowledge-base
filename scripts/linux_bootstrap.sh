#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command '$1' is not installed"
}

require_command docker
require_command curl
require_command openssl

docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is not available"
docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable or current user lacks permission"

if [[ ! -f .env ]]; then
  umask 077
  postgres_password="$(openssl rand -hex 24)"
  minio_password="$(openssl rand -hex 24)"
  auth_pepper="$(openssl rand -hex 32)"
  temporary_env="$(mktemp .env.XXXXXX)"
  trap 'rm -f -- "${temporary_env:-}"' EXIT
  sed \
    -e "s|^ACKB_POSTGRES_PASSWORD=.*|ACKB_POSTGRES_PASSWORD=${postgres_password}|" \
    -e "s|^ACKB_DATABASE_URL=.*|ACKB_DATABASE_URL=postgresql+asyncpg://ackb:${postgres_password}@127.0.0.1:5432/ackb|" \
    -e "s|^ACKB_AUTH_THROTTLE_PEPPER=.*|ACKB_AUTH_THROTTLE_PEPPER=${auth_pepper}|" \
    -e 's|^ACKB_MINIO_ROOT_USER=.*|ACKB_MINIO_ROOT_USER=ackb-minio|' \
    -e "s|^ACKB_MINIO_ROOT_PASSWORD=.*|ACKB_MINIO_ROOT_PASSWORD=${minio_password}|" \
    -e 's|^ACKB_MINIO_ACCESS_KEY=.*|ACKB_MINIO_ACCESS_KEY=ackb-minio|' \
    -e "s|^ACKB_MINIO_SECRET_KEY=.*|ACKB_MINIO_SECRET_KEY=${minio_password}|" \
    .env.example >"$temporary_env"
  mv -- "$temporary_env" .env
  chmod 600 .env
  trap - EXIT
  unset postgres_password minio_password auth_pepper
  printf 'Created local .env with generated credentials (values were not printed).\n'
elif grep -q 'replace-with' .env; then
  fail ".env still contains placeholder values; remove it to regenerate safely or replace them manually"
fi

docker compose config --quiet
docker compose up --build --detach

http_port="$(sed -n 's/^ACKB_HTTP_PORT=//p' .env | tail -n 1)"
http_port="${http_port:-8080}"
base_url="http://127.0.0.1:${http_port}"

for attempt in $(seq 1 60); do
  if curl --fail --silent --show-error --max-time 5 "${base_url}/health" >/dev/null \
    && curl --fail --silent --show-error --max-time 5 "${base_url}/ready" >/dev/null \
    && curl --fail --silent --show-error --max-time 5 "${base_url}/" >/dev/null; then
    docker compose ps
    printf 'Arduino Component Knowledge Base is ready at %s\n' "$base_url"
    printf 'Create the first administrator with:\n'
    printf '  docker compose run --rm backend ackb-bootstrap-admin --login admin --display-name "Initial Administrator"\n'
    exit 0
  fi
  if [[ "$attempt" -eq 60 ]]; then
    docker compose ps >&2
    docker compose logs --tail=100 backend reverse-proxy postgres redis minio >&2
    fail "stack did not become ready within 300 seconds"
  fi
  sleep 5
done
