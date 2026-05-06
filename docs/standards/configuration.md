---
title: Configuration
description: Environment variables, config files, and priority chain for roxabi-cortex.
---

# Configuration

## Environment Variables

Variables are loaded from `.env` at the workspace root (never committed). Podman secrets handle sensitive values in deployed containers.

| Variable | Required | Default | Description |
|---|:---:|---|---|
| `CORTEX_INSIGHT_DB` | No | `~/.cortex/insight.duckdb` | DuckDB path for cortex-insight |
| `CORTEX_MEMORY_DB` | No | `~/.cortex/memory.duckdb` | DuckDB path for cortex-memory |
| `NATS_URL` | Yes | — | NATS server URL (e.g. `nats://lyra-nats:4222`) |
| `NATS_NKEY_SEED_INSIGHT` | Yes (deploy) | — | nkey seed for cortex-insight NATS auth (Podman secret in prod) |
| `NATS_NKEY_SEED_MEMORY` | Yes (deploy) | — | nkey seed for cortex-memory NATS auth (Podman secret in prod) |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity (`DEBUG`/`INFO`/`WARNING`/`ERROR`) |

> TODO: Extend this table as env vars are defined during Phase 1 implementation.

## Config Files

| File | Purpose | Committed? |
|---|---|:---:|
| `.claude/stack.yml` | dev-core stack config | Yes |
| `.claude/dev-core.yml` | dev-core plugin config (GitHub IDs, board #26) | No |
| `.env` | per-machine env vars + local secrets | No |
| `pyproject.toml` (root) | uv workspace, ruff + pyright config | Yes |
| `packages/insight/pyproject.toml` | cortex-insight deps + entry point | Yes |
| `packages/memory/pyproject.toml` | cortex-memory deps + entry point | Yes |
| `packages/insight/deploy/quadlet/cortex-insight.container` | Quadlet unit (production) | Yes |
| `packages/memory/deploy/quadlet/cortex-memory.container` | Quadlet unit (production) | Yes |

`.gitignore` excludes: `.env*`, `__pycache__`, `*.pyc`, `.claude/dev-core.yml`, `*.duckdb`.

## Priority Chain

1. Podman secret (highest — production nkeys, never in env)
2. Environment variable (set in shell or `.env`)
3. Default value in code (lowest)

## Quadlet Secrets (Production)

NATS nkeys are injected via Podman secrets (not env vars):

```ini
# cortex-insight.container (excerpt)
Secret=nkey-cortex-insight,type=env,target=NATS_NKEY_SEED_INSIGHT
Secret=nkey-cortex-memory,type=env,target=NATS_NKEY_SEED_MEMORY
```

Manage secrets with: `podman secret create nkey-cortex-insight <file>`

## AI Quick Reference

- NEVER commit `.env` or any file containing secrets or nkeys.
- ALWAYS use Podman secrets for NATS nkeys in deployed containers (never plain env in Quadlet).
- PREFER `~/.cortex/{insight,memory}.duckdb` as the default DB path — override via env var for testing.
