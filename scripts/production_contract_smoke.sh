#!/usr/bin/env bash
set -Eeuo pipefail

readonly ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_dir="$(mktemp -d)"
trap 'rm -rf -- "$temporary_dir"' EXIT

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -subj '/CN=kb.test.internal' \
  -addext 'subjectAltName=DNS:kb.test.internal,DNS:minio' \
  -keyout "$temporary_dir/tls.key" \
  -out "$temporary_dir/tls.crt" >/dev/null 2>&1
chmod 600 "$temporary_dir/tls.key"

sed \
  -e 's|replace-with-production-postgres-password|ci-postgres-placeholder|' \
  -e 's|replace-with-production-minio-user|ci-minio-user|' \
  -e 's|replace-with-production-minio-password|ci-minio-password|' \
  -e 's|replace-with-at-least-32-random-characters|ci-only-pepper-value-00000000000000|' \
  -e 's|replace-with-internal-dns-name|kb.test.internal|' \
  -e 's|replace-with-static-ip|127.0.0.1|' \
  -e "s|replace-with-absolute-edge-certificate-path|$temporary_dir/tls.crt|" \
  -e "s|replace-with-absolute-edge-private-key-path|$temporary_dir/tls.key|" \
  -e "s|replace-with-absolute-minio-certificate-path|$temporary_dir/tls.crt|" \
  -e "s|replace-with-absolute-minio-private-key-path|$temporary_dir/tls.key|" \
  -e "s|replace-with-absolute-ca-bundle-path|$temporary_dir/tls.crt|" \
  "$ROOT_DIR/.env.production.example" >"$temporary_dir/environment"

docker compose \
  --env-file "$temporary_dir/environment" \
  -f "$ROOT_DIR/compose.yaml" \
  -f "$ROOT_DIR/compose.production.yaml" \
  config --quiet

docker run --rm \
  --env ACKB_INTERNAL_HOSTNAME=kb.test.internal \
  --volume "$ROOT_DIR/deploy/reverse-proxy/internal-https.conf.template:/etc/nginx/templates/default.conf.template:ro" \
  --volume "$temporary_dir/tls.crt:/etc/nginx/tls/tls.crt:ro" \
  --volume "$temporary_dir/tls.key:/etc/nginx/tls/tls.key:ro" \
  nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236 \
  nginx -t

printf 'Production Compose and nginx contract smoke test passed.\n'
