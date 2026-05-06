---
title: Architecture Patterns
description: Recurring design patterns derived from the accepted ADRs.
---

# Architecture Patterns

Patterns codified in the [ADRs](../adr/README.md). See each linked ADR for full rationale and alternatives considered.

## Lake / Warehouse Split (ADR-003)

Classic data-engineering pattern: **insight = lake** (append-heavy, schema-on-read, source-specific), **memory = warehouse** (schema-on-write, generic, consumer-facing).

| insight (lake) | memory (warehouse) |
|---|---|
| Stores all raw events | Stores entity graph + relations |
| Source-specific pipelines | Source-agnostic consolidation |
| Rewrites are cheap | Schema changes are versioned |
| Publishes `Observation` | Consumes `Observation` |

Boundary rule: **insight never stores the graph; memory never parses raw source data.**

## Producer Model (ADR-004)

All external producers (Claude Code JSONL, git/gh, NATS Lyra, mail, Telegram, voice) publish to **cortex-insight only**. Memory never receives raw events.

```
External producers → roxabi.insight.events.publish.{source} → cortex-insight
cortex-insight     → roxabi.memory.observations.publish      → cortex-memory
```

Adding a new source = new parser + new pipeline in insight only. Memory is unchanged.

## Observation Contract (ADR-005)

The publish boundary between insight and memory is the `Observation` — a typed, encoded fact, not yet resolved against the graph. Inspired by the hippocampus (encode) → cortex (consolidate) biological model.

```python
class Observation(BaseModel):
    id: ULID
    source: str           # "claude-code-jsonl" | "mail" | "telegram" | …
    source_ref: str
    timestamp: int        # epoch ms
    category: ObservationCategory  # interaction | finding | decision | artifact | …
    actors: list[ActorRef]
    topic: list[str] | None
    sentiment: str | None
    payload_typed: dict
    correlation: dict
```

Insight encodes (knows the source). Memory consolidates (knows the graph). Neither knows both.

## Monorepo Workspace (ADR-008)

Single repo `roxabi-cortex` with `packages/{insight,memory}` as uv workspace members. One release line, one CI, one clone.

Import discipline enforced via `pyproject.toml` deps (cross-package imports are not declared → fail at import time). Communication is NATS-only via `roxabi-contracts`.

Integration tests mount both services + local NATS; they are the only valid cross-package tests.

## DuckDB v1 — Conditional (ADR-011)

DuckDB everywhere for v1. Triggers for memory → KuzuDB migration:

| Trigger | Threshold |
|---|---|
| `assemble` p95 latency | > 200 ms sustained |
| Write/read contention on memory DB | observed lock contention |
| Relations count | > 100 000 |
| Entity count | > 10 000 |

Instrument memory from day 1. Do not migrate without a superseding ADR.

## Podman + Quadlet (ADR-002)

Both services deploy as rootless Podman containers managed by systemd via Quadlet `.container` units. Pattern is identical to existing Lyra/voiceCLI services.

| Aspect | Detail |
|---|---|
| Images | `ghcr.io/roxabi/cortex-{insight,memory}:staging` |
| Quadlet units | `packages/{insight,memory}/deploy/quadlet/cortex-*.container` |
| Network | `roxabi.network` (shared with NATS) |
| Secrets | Podman secrets for NATS nkeys |
| Hardening | `NoNewPrivileges`, `ReadOnly`, `DropCapability=all`, `UserNS=keep-id` |
| Storage | bind mount `%h/.cortex/{insight,memory}.duckdb` |

Ops interface: `make cortex-{insight,memory} {start,stop,reload,status,logs}`.

## Contracts as Protocol SSoT (ADR-006)

NATS subjects and message schemas live in `roxabi-contracts` (`lyra/packages/roxabi-contracts/`), not in the service implementations. Both `cortex-insight` and `cortex-memory` depend on `roxabi-contracts` via uv GitHub source.

Never define NATS subjects or Pydantic message schemas inside a service package.

## See Also

- [Architecture Overview](index.md)
- [ADR index](../adr/README.md)
- [Ubiquitous Language](ubiquitous-language.md)
