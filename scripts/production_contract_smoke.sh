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
  -e "s|replace-with-absolute-edge-certificate-path|$temporary_dir/tls.crt|" \
  -e "s|replace-with-absolute-edge-private-key-path|$temporary_dir/tls.key|" \
  -e "s|replace-with-absolute-minio-certificate-path|$temporary_dir/tls.crt|" \
  -e "s|replace-with-absolute-minio-private-key-path|$temporary_dir/tls.key|" \
  -e "s|replace-with-absolute-ca-bundle-path|$temporary_dir/tls.crt|" \
  -e 's|replace-with-deployed-commit-sha|0123456789abcdef0123456789abcdef01234567|' \
  -e 's|replace-with-ISO-8601-build-date|2026-07-29T00:00:00Z|' \
  "$ROOT_DIR/.env.production.example" >"$temporary_dir/environment"
chmod 600 "$temporary_dir/environment"

docker compose \
  --env-file "$temporary_dir/environment" \
  -f "$ROOT_DIR/compose.yaml" \
  -f "$ROOT_DIR/compose.production.yaml" \
  config --quiet

docker run --rm \
  --read-only \
  --cap-drop ALL \
  --cap-add CHOWN \
  --cap-add DAC_OVERRIDE \
  --cap-add SETGID \
  --cap-add SETUID \
  --security-opt no-new-privileges \
  --tmpfs /etc/nginx/conf.d:rw,noexec,nosuid,nodev,size=1m,mode=1777 \
  --tmpfs /var/cache/nginx:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --tmpfs /var/run:rw,noexec,nosuid,nodev,size=1m,mode=1777 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --env ACKB_INTERNAL_HOSTNAME=kb.test.internal \
  --add-host backend:127.0.0.1 \
  --add-host frontend:127.0.0.1 \
  --add-host minio:127.0.0.1 \
  --volume "$ROOT_DIR/deploy/reverse-proxy/internal-https.conf.template:/etc/nginx/templates/default.conf.template:ro" \
  --volume "$temporary_dir/tls.crt:/etc/nginx/tls/tls.crt:ro" \
  --volume "$temporary_dir/tls.key:/etc/nginx/tls/tls.key:ro" \
  --volume "$temporary_dir/tls.crt:/etc/nginx/ca/ca-bundle.crt:ro" \
  --entrypoint /bin/sh \
  nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236 \
  -c "envsubst '\$ACKB_INTERNAL_HOSTNAME' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -t"

docker run --rm \
  --user 101:101 \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /var/cache/nginx:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --tmpfs /var/run:rw,noexec,nosuid,nodev,size=1m,mode=1777 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --volume "$ROOT_DIR/frontend/deploy/default.conf:/etc/nginx/conf.d/default.conf:ro" \
  --entrypoint nginx \
  nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236 \
  -t

printf 'Production Compose and nginx contract smoke test passed.\n'
