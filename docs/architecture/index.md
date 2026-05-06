---
title: Architecture
description: Pointer to the authoritative architecture document and decision log.
---

# Architecture

The authoritative architecture document is **[docs/ARCHITECTURE.md](../ARCHITECTURE.md)**.

It covers: system vision, full topology diagram, component breakdown (cortex-insight lake + ETL, cortex-memory warehouse + consolidation), canonical data flows (Claude Code → insight → memory → consumer), storage decisions, NATS contracts, Podman + Quadlet deployment, and the implementation status.

Architecture decisions are recorded in **[docs/adr/](../adr/README.md)** (ADR-001 through ADR-011). The ADRs are the source of truth for all structural choices; `ARCHITECTURE.md` is the readable summary. When there is a conflict, the ADR wins.

## See Also

- [Patterns](patterns.md) — lake/warehouse split, Observation contract, producer model, DuckDB v1, Podman+Quadlet
- [Ubiquitous Language](ubiquitous-language.md) — shared domain vocabulary
- [Configuration](../standards/configuration.md) — environment variables, config files
- [Deployment](../guides/deployment.md) — Podman + Quadlet ops
