---
title: Troubleshooting
description: Common issues and fixes for cortex-insight and cortex-memory.
---

# Troubleshooting

> **TODO (Phase 1):** This guide will be populated once `cortex-insight` and `cortex-memory` have a working implementation. The sections below are scaffolded based on the known architecture; fill in symptoms, causes, and fixes after the first operational deployment.

## Service Won't Start

> TODO: Document `systemctl --user status cortex-insight.service` output patterns and fixes after Quadlet units are installed.

Likely causes: Quadlet unit not installed, `roxabi.network` not created, DuckDB path permissions, NATS nkey secret missing.

## NATS Connection Failures

> TODO: Document connection error messages from nats-py and resolution steps.

Check: `lyra-nats` container running, `roxabi.network` Podman network exists, nkey secret correct, NATS URL env var set.

## DuckDB Issues

> TODO: Document DuckDB lock contention symptoms and fixes after daemon operation is observed.

Known concern (ADR-011): DuckDB is single-writer. If insight and memory somehow share a DB file, writes will fail. Each service has its own file (`~/.cortex/insight.duckdb` and `~/.cortex/memory.duckdb`).

## Ingest Pipeline

> TODO: Document cocoindex file-watcher issues, JSONL parse errors, sanitization rejections after Phase 1 implementation.

## Memory Graph

> TODO: Document Retain Job failures, schema_fit anomalies, decay recalc errors after implementation.

## Development Environment

| Symptom | Fix |
|---|---|
| `uv sync` fails | Verify `requires-python = ">=3.13"` matches installed Python version |
| pyright strict errors | Check `pyproject.toml` `[tool.pyright]` config; run `uv run pyright` |
| ruff check failures | Run `uv run ruff check --fix` |
| Tests can't find `cortex_insight` | Run `uv sync` from workspace root first |

## See Also

- [Deployment Guide](deployment.md) — Quadlet unit setup and ops commands
- [Configuration](../standards/configuration.md) — env vars and secrets
- [ADR-002](../adr/ADR-002-deployment-podman-quadlet.md) — deployment pattern
- [ADR-011](../adr/ADR-011-storage-duckdb-v1.md) — DuckDB concurrency constraints
