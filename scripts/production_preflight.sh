#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="${1:-${ROOT_DIR}/.env.production}"

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command '$1' is not installed"
}

read_setting() {
  local name="$1"
  local value
  value="$(sed -n "s/^${name}=//p" "$ENV_FILE" | tail -n 1)"
  [[ -n "$value" ]] || fail "$name is missing from $ENV_FILE"
  [[ "$value" != *replace-with* ]] || fail "$name still contains a placeholder"
  printf '%s' "$value"
}

require_secret() {
  local name="$1"
  local value
  value="$(read_setting "$name")"
  [[ ${#value} -ge 32 ]] || fail "$name must contain at least 32 characters"
  [[ "$value" =~ ^[A-Za-z0-9._~-]+$ ]] \
    || fail "$name must use URL-safe characters: letters, digits, dot, underscore, tilde or hyphen"
}

verify_certificate() {
  local certificate="$1"
  local expected_host="$2"
  local ca_bundle="$3"
  local private_key="$4"
  [[ "$certificate" = /* && -f "$certificate" ]] || fail "certificate path must be absolute and readable"
  openssl x509 -in "$certificate" -noout -checkend 604800 >/dev/null \
    || fail "certificate for $expected_host expires within seven days"
  openssl x509 -in "$certificate" -noout -checkhost "$expected_host" >/dev/null \
    || fail "certificate does not contain $expected_host in subjectAltName"
  openssl verify -CAfile "$ca_bundle" "$certificate" >/dev/null \
    || fail "certificate for $expected_host is not trusted by ACKB_CA_BUNDLE_FILE"
  openssl pkey -in "$private_key" -noout -check >/dev/null 2>&1 \
    || fail "private key for $expected_host is invalid"
  cmp \
    <(openssl x509 -in "$certificate" -pubkey -noout) \
    <(openssl pkey -in "$private_key" -pubout) >/dev/null \
    || fail "certificate and private key do not match for $expected_host"
}

for command in awk cmp cut docker curl getent grep ip openssl sed stat tr; do
  require_command "$command"
done

[[ -r /etc/os-release ]] || fail "/etc/os-release is unavailable"
# shellcheck disable=SC1091
source /etc/os-release
[[ "${ID:-}" == "ubuntu" ]] || fail "corporate deployment baseline requires Ubuntu Server"
[[ -f "$ENV_FILE" ]] || fail "production environment file not found: $ENV_FILE"
[[ "$(stat -c '%a' "$ENV_FILE")" =~ ^[46]00$ ]] \
  || fail "production environment file mode must be 400 or 600"
grep -q 'replace-with' "$ENV_FILE" && fail "$ENV_FILE still contains placeholder values"
docker compose version >/dev/null 2>&1 || fail "Docker Compose plugin is unavailable"
docker info >/dev/null 2>&1 || fail "Docker daemon is unavailable or permission is denied"

internal_hostname="$(read_setting ACKB_INTERNAL_HOSTNAME)"
bind_address="$(read_setting ACKB_BIND_ADDRESS)"
ca_bundle="$(read_setting ACKB_CA_BUNDLE_FILE)"
edge_certificate="$(read_setting ACKB_EDGE_TLS_CERT_FILE)"
edge_key="$(read_setting ACKB_EDGE_TLS_KEY_FILE)"
minio_certificate="$(read_setting ACKB_MINIO_TLS_CERT_FILE)"
minio_key="$(read_setting ACKB_MINIO_TLS_KEY_FILE)"
postgres_owner="$(read_setting ACKB_POSTGRES_USER)"
postgres_runtime="$(read_setting ACKB_POSTGRES_RUNTIME_USER)"
postgres_backup="$(read_setting ACKB_POSTGRES_BACKUP_USER)"
minio_root="$(read_setting ACKB_MINIO_ROOT_USER)"
minio_runtime="$(read_setting ACKB_MINIO_ACCESS_KEY)"
commit_sha="$(read_setting ACKB_COMMIT_SHA)"
build_date="$(read_setting ACKB_BUILD_DATE)"

for secret_name in \
  ACKB_POSTGRES_PASSWORD \
  ACKB_POSTGRES_RUNTIME_PASSWORD \
  ACKB_POSTGRES_BACKUP_PASSWORD \
  ACKB_MINIO_ROOT_PASSWORD \
  ACKB_MINIO_SECRET_KEY \
  ACKB_REDIS_PASSWORD \
  ACKB_AUTH_THROTTLE_PEPPER; do
  require_secret "$secret_name"
done

[[ "$postgres_runtime" =~ ^[a-z_][a-z0-9_]{2,62}$ ]] \
  || fail "ACKB_POSTGRES_RUNTIME_USER must be a simple lowercase PostgreSQL role"
[[ "$postgres_runtime" != "$postgres_owner" ]] \
  || fail "runtime PostgreSQL role must differ from bootstrap owner"
[[ ! "$postgres_runtime" =~ ^(postgres|root|admin|administrator|demo|test|ackb)$ ]] \
  || fail "ACKB_POSTGRES_RUNTIME_USER is not a dedicated runtime role"
[[ "$postgres_backup" =~ ^[a-z_][a-z0-9_]{2,62}$ ]] \
  || fail "ACKB_POSTGRES_BACKUP_USER must be a simple lowercase PostgreSQL role"
[[ "$postgres_backup" != "$postgres_owner" && "$postgres_backup" != "$postgres_runtime" ]] \
  || fail "backup PostgreSQL role must differ from owner and runtime roles"
[[ ! "$postgres_backup" =~ ^(postgres|root|admin|administrator|demo|test|ackb)$ ]] \
  || fail "ACKB_POSTGRES_BACKUP_USER is not a dedicated backup role"
[[ "$minio_runtime" != "$minio_root" ]] \
  || fail "runtime MinIO access key must differ from root access key"
[[ ! "$minio_runtime" =~ ^(minioadmin|root|admin|administrator|demo|test)$ ]] \
  || fail "ACKB_MINIO_ACCESS_KEY is not a dedicated runtime identity"
[[ "$commit_sha" =~ ^[0-9a-f]{40}$ ]] \
  || fail "ACKB_COMMIT_SHA must be the full lowercase deployed commit SHA"
[[ "$build_date" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] \
  || fail "ACKB_BUILD_DATE must use UTC ISO-8601 form YYYY-MM-DDTHH:MM:SSZ"

[[ "$internal_hostname" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] \
  || fail "ACKB_INTERNAL_HOSTNAME is not a valid DNS hostname"
[[ "$bind_address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] \
  || fail "ACKB_BIND_ADDRESS must be an IPv4 address"
ip -brief address show | awk '{print $3}' | tr ' ' '\n' | cut -d/ -f1 | grep -Fxq "$bind_address" \
  || fail "ACKB_BIND_ADDRESS is not assigned to this server"
getent ahostsv4 "$internal_hostname" | awk '{print $1}' | grep -Fxq "$bind_address" \
  || fail "internal DNS does not resolve ACKB_INTERNAL_HOSTNAME to ACKB_BIND_ADDRESS"

[[ "$ca_bundle" = /* && -f "$ca_bundle" ]] || fail "ACKB_CA_BUNDLE_FILE must be absolute and readable"
[[ "$edge_key" = /* && -f "$edge_key" ]] || fail "edge private key path must be absolute and readable"
[[ "$minio_key" = /* && -f "$minio_key" ]] || fail "MinIO private key path must be absolute and readable"
[[ "$(stat -c '%a' "$edge_key")" =~ ^[46]00$ ]] || fail "edge private key mode must be 400 or 600"
[[ "$(stat -c '%a' "$minio_key")" =~ ^[46]00$ ]] || fail "MinIO private key mode must be 400 or 600"

verify_certificate "$edge_certificate" "$internal_hostname" "$ca_bundle" "$edge_key"
verify_certificate "$minio_certificate" minio "$ca_bundle" "$minio_key"

cd "$ROOT_DIR"
docker compose \
  --env-file "$ENV_FILE" \
  -f compose.yaml \
  -f compose.production.yaml \
  config --quiet

printf 'Production preflight passed for %s on %s. No system settings were changed.\n' \
  "$internal_hostname" "$bind_address"
