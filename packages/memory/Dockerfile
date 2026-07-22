# syntax=docker/dockerfile:1
# cortex-memory — long-term memory NATS satellite
#
# Build (with factory monorepo next door for contracts/nats):
#   podman build -f packages/memory/Dockerfile \
#     --build-context factory=../roxabi-factory \
#     -t ghcr.io/roxabi/cortex-memory:staging \
#     packages/memory
#
# Or from packages/memory with factory packages vendored under ./vendor/.

FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Prefer additional build-context "factory" (roxabi-factory monorepo root).
# Fallback: vendor/ copied into the memory package context.
COPY --from=factory packages/roxabi-contracts /deps/roxabi-contracts
COPY --from=factory packages/roxabi-nats /deps/roxabi-nats

COPY pyproject.toml ./
COPY src/ src/

# Point uv sources at vendored workspace packages for a hermetic image build.
RUN python3 - <<'PY'
from pathlib import Path
p = Path("pyproject.toml")
text = p.read_text()
# Replace path/git sources for roxabi-* with /deps paths
import re
text = re.sub(
    r"roxabi-contracts\s*=\s*\{[^}]+\}",
    'roxabi-contracts = { path = "/deps/roxabi-contracts" }',
    text,
)
text = re.sub(
    r"roxabi-nats\s*=\s*\{[^}]+\}",
    'roxabi-nats = { path = "/deps/roxabi-nats" }',
    text,
)
p.write_text(text)
print(p.read_text())
PY

RUN uv sync --no-dev --no-editable

FROM ghcr.io/roxabi/base:latest AS runtime

USER root

# Match factory hub keep-id mapping (uid 1500 → host user)
RUN useradd -u 1500 -m cortex \
    && mkdir -p /home/cortex/.cortex /data \
    && chown -R cortex:cortex /home/cortex /data

COPY --from=builder --chown=cortex:cortex /app /app

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV CORTEX_MEMORY_DB=/data/memory.db

USER cortex

ENTRYPOINT ["cortex-memory"]
CMD ["serve", "--db", "/data/memory.db"]
