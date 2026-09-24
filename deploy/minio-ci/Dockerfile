# Isolated linux/amd64 CI only; not a production image.
FROM golang:1.26-alpine@sha256:66f9a494af2b76ecb3eab75ff47166df61caec6d200c59d556b77327493d83a8 AS builder
RUN apk add --no-cache ca-certificates curl
ENV CGO_ENABLED=0 GOTOOLCHAIN=local GOFLAGS=-mod=readonly
WORKDIR /src/minio
# Official RELEASE.2025-10-15T17-29-55Z, including the STS policy security fix.
RUN curl --fail --location --retry 3 https://codeload.github.com/minio/minio/tar.gz/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a -o /tmp/minio.tar.gz \
    && echo '45521908307306e925c98d629e1c17d78c8b72b6ee242b1bfb1409f7d8ee5841  /tmp/minio.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/minio.tar.gz --strip-components=1 \
    && go mod download && go mod verify \
    && go build -p 2 -trimpath -o /out/minio .
WORKDIR /src/mc
# Official RELEASE.2025-08-13T08-35-41Z.
RUN curl --fail --location --retry 3 https://codeload.github.com/minio/mc/tar.gz/7394ce0dd2a80935aded936b09fa12cbb3cb8096 -o /tmp/mc.tar.gz \
    && echo '95cd293c7119f16921a6dc515a1fb74a2227f19fd994b9c8b770a154e802ac44  /tmp/mc.tar.gz' | sha256sum -c - \
    && tar -xzf /tmp/mc.tar.gz --strip-components=1 \
    && go mod download && go mod verify \
    && go build -p 2 -trimpath -o /out/mc .

FROM alpine:3.23@sha256:1f3591b8a02ea153f41c5bba878ad477f63ab3d19349762cb77504db02a23e15
RUN apk add --no-cache ca-certificates
COPY --from=builder /out/ /usr/bin/
COPY --from=builder /src/minio/LICENSE /licenses/minio/LICENSE
COPY --from=builder /src/mc/LICENSE /licenses/mc/LICENSE
ENV MINIO_UPDATE=off
EXPOSE 9000 9001
ENTRYPOINT ["/usr/bin/minio"]
CMD ["server", "/data"]
