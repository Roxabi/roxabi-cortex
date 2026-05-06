# syntax=docker/dockerfile:1
# cortex-insight — lake + ETL service
# Pattern: multi-stage builder + runtime · base ghcr.io/roxabi/base · cf. ADR-002

FROM python:3.13-slim AS builder

# Install system deps (git needed for GitHub-sourced Python deps)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Layer caching: copy lockfile + pyproject first, then source
COPY pyproject.toml ./
COPY src/ src/
RUN uv sync --no-dev

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM ghcr.io/roxabi/base:latest AS runtime

USER root

# UID 1500 pinned per ADR-053 (Quadlet container UID stability)
RUN useradd -u 1500 -m cortex && mkdir -p /home/cortex/.cortex

COPY --from=builder --chown=cortex:cortex /app /app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

USER cortex

# TODO: HEALTHCHECK once health endpoint is implemented
# HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
#   CMD cortex-insight health || exit 1

# TODO: ENTRYPOINT once cli.py is implemented
ENTRYPOINT ["python", "-c", "print('cortex-insight stub — implement me')"]
