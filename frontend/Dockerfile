# syntax=docker/dockerfile:1.7

FROM node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts ./
COPY public ./public
COPY src ./src
ARG VITE_APP_VERSION=0.20.0
ARG VITE_COMMIT_SHA=unknown
ARG VITE_BUILD_DATE=unknown
ENV VITE_APP_VERSION=${VITE_APP_VERSION} \
    VITE_COMMIT_SHA=${VITE_COMMIT_SHA} \
    VITE_BUILD_DATE=${VITE_BUILD_DATE}
RUN npm run build

FROM nginx:1.28-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236 AS runtime

COPY deploy/default.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 8080
