# syntax=docker/dockerfile:1.7

FROM python:3.13-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build

COPY pyproject.toml README.md LICENCE THIRD_PARTY_NOTICES.md MANIFEST.in alembic.ini ./
COPY docs ./docs
COPY migrations ./migrations
COPY src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13-slim-bookworm@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends --yes ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system ackb \
    && adduser --system --ingroup ackb --home /app ackb

WORKDIR /app
COPY --from=builder /wheels /wheels
RUN python -m pip install /wheels/*.whl && rm -rf /wheels
COPY --chown=ackb:ackb alembic.ini ./alembic.ini
COPY --chown=ackb:ackb migrations ./migrations

USER ackb
EXPOSE 8000

CMD ["uvicorn", "arduino_component_kb.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*", "--no-access-log"]
