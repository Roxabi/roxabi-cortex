---
title: Backend Patterns
description: Python service conventions for cortex-insight and cortex-memory.
---

# Backend Patterns

Project-specific patterns for `cortex-insight` and `cortex-memory`. See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full picture.

> Universal patterns (error handling, retry logic, async patterns) are embedded in the `backend-dev` agent.
> This file documents **cortex-specific** choices.

## Stack Summary

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| Package manager | uv + hatchling · uv workspace |
| CLI | typer (both services) |
| Storage | DuckDB v1 (direct driver, no ORM) — [ADR-011](../adr/ADR-011-storage-duckdb-v1.md) |
| Messaging | nats-py ≥ 2.7 |
| Contracts | `roxabi-contracts` — `insight.py` + `memory.py` — [ADR-006](../adr/ADR-006-contracts-package-extension.md) |
| Parsing | polars |
| Incremental ingest | cocoindex (Lane 1 JSONL) |

## Service Shape

Each service (`cortex_insight`, `cortex_memory`) is a **CLI + NATS worker**. No HTTP framework.

```
src/cortex_{insight,memory}/
├── cli.py          # typer app — all commands wired here
├── __init__.py
├── ingest/         # (insight) parsers per source
├── raw/            # (insight) raw event store (DuckDB, append-only)
├── pipelines/      # (insight) behavioral/, relationship/, …
├── encode/         # (insight) events → Observation typed facts
├── publish/        # (insight) NATS publisher
├── api/            # (memory) NATS subscriber + req/reply handlers
├── retain/         # (memory) Retain Job — consolidation
├── graph/          # (memory) entities + relations CRUD
├── compiled/       # (memory) compiled truth per entity
├── assemble/       # (memory) DAG-aware context retrieval
└── actuate/        # (memory) approval queue + auto-PR
```

Quality gates (from `stack.yml`): max 300 lines/file · max 12 files/folder.

## Typer CLI Shape

Both services expose a single `app = typer.Typer()` in `cli.py`. Entry point declared in `pyproject.toml`:

```toml
[project.scripts]
cortex-insight = "cortex_insight.cli:app"
cortex-memory  = "cortex_memory.cli:app"
```

Commands are registered as sub-groups or direct commands on `app`. Keep `cli.py` thin — delegate to service modules.

## NATS Subjects (via roxabi-contracts)

NEVER hardcode subject strings. ALWAYS import from `roxabi_contracts.{insight,memory}`.

| Direction | Subject | Contract |
|---|---|---|
| Producer → insight | `roxabi.insight.events.publish.{source}` | `RawEventEnvelope` |
| insight → memory | `roxabi.memory.observations.publish` | `Observation` |
| Consumer → memory | `roxabi.memory.query.entities` | `EntityQueryRequest/Response` |
| Consumer → memory | `roxabi.memory.query.assemble` | `AssembleRequest/Response` |
| Consumer → memory | `roxabi.memory.query.compiled` | compiled truth lookup |
| Approval ops | `roxabi.memory.actuate.approve` | approval queue |

## Service Boundary (ADR-003 / ADR-008)

| Rule | Enforcement |
|---|---|
| `cortex_insight.*` NEVER imports `cortex_memory.*` | not in `packages/insight/pyproject.toml` deps |
| `cortex_memory.*` NEVER imports `cortex_insight.*` | not in `packages/memory/pyproject.toml` deps |
| Cross-service communication via NATS + contracts only | both packages depend on `roxabi-contracts` |

## DuckDB Access Patterns

- **insight** (`~/.cortex/insight.duckdb`): append-heavy raw events, OLAP scans, polars integration.
- **memory** (`~/.cortex/memory.duckdb`): entity/relation lookups, decay batch updates, graph traversal via recursive CTE.
- One DuckDB connection per service process (single-writer model).
- Instrument latency + lock waits in memory from day 1 — needed for ADR-011 trigger evaluation.
- NEVER share a DuckDB file between insight and memory.

## Sanitization

Raw events from all sources pass through:
1. trufflehog `--no-verification` (secret detection)
2. regex patterns (PII, paths)
3. path normalizer

Sanitization lives in `cortex_insight.ingest`. Memory never receives unsanitized data.

## AI Quick Reference

- ALWAYS import NATS subjects from `roxabi_contracts` — NEVER hardcode subject strings.
- NEVER import across the insight/memory boundary — communicate via NATS + `Observation` contract only.
- ALWAYS pass raw events through the sanitization pipeline before writing to `raw_events` table.
- PREFER polars for batch transforms in insight pipelines; DuckDB queries for aggregations and reports.
- NEVER write a service that requires an HTTP server — CLIs + NATS workers only.
