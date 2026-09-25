# Isolated CI MinIO

The previously pinned Quay image now returns `unauthorized` to anonymous CI.
MinIO's [official release instructions](https://github.com/minio/minio/releases/tag/RELEASE.2025-10-15T17-29-55Z)
recommend building containers from source.

This linux/amd64 test image builds MinIO and its `mc` client from official release
commits, verifies both source archive SHA-256 checksums and Go module checksums,
and pins its Go/Alpine base images by digest. Both upstream AGPL license files
are included. It is built locally in each CI job, not pushed to a registry.

```sh
docker build --tag ackb-ci/minio:9e49d5e7a648 deploy/minio-ci
ACKB_CI_MINIO_SOURCE=true bash scripts/clean_stack_smoke.sh
ACKB_CI_MINIO_SOURCE=true bash scripts/production_identity_smoke.sh
```

The explicit flag selects `compose.ci.yaml` and, for the TLS/least-privilege
identity test, `compose.ci-identity.yaml`. `pull_policy: never` fails if the
locally built image is missing. All existing health, S3, TLS and authorization
checks remain enabled. Default deployment Compose files are unchanged; these
overrides must not be used for production. Fixing the unavailable production
image requires a separate deployment decision.
