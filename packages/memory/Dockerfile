# syntax=docker/dockerfile:1
# cortex-memory — long-term memory NATS satellite
# Pattern: multi-stage builder + runtime · base ghcr.io/roxabi/base

FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Local monorepo packages (path sources in pyproject) — copy when building
# from a context that includes factory packages, OR rely on git staging pins.
COPY pyproject.toml ./
COPY src/ src/
# If building with context that vendors contracts: COPY factory-contracts/ ...
RUN uv sync --no-dev --no-editable

FROM ghcr.io/roxabi/base:latest AS runtime

USER root

# UID 1504 per Roxabi UID registry — distinct from factory (1500)
RUN useradd -u 1504 -m cortex && mkdir -p /home/cortex/.cortex /data \
    && chown -R cortex:cortex /home/cortex /data

COPY --from=builder --chown=cortex:cortex /app /app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV CORTEX_MEMORY_DB=/data/memory.db

USER cortex

ENTRYPOINT ["cortex-memory"]
CMD ["serve", "--db", "/data/memory.db"]
