---
title: Ubiquitous Language
description: Domain glossary for roxabi-cortex — lifted from CLAUDE.md Key Concepts.
---

# Ubiquitous Language

Shared domain vocabulary. Source of truth: `CLAUDE.md` "Key concepts" section.

## Glossary

| Term | Definition |
|---|---|
| **Cortex** | The complete ecosystem (ADR-001) — cortex-insight + cortex-memory + contracts + producers + consumers. |
| **Insight** | Service: lake + encoding. Receives all raw events from external producers, runs domain-specific pipelines, produces typed Observations. |
| **Memory** | Service: warehouse + consolidation + serve. Receives Observations, consolidates into the entity graph with decay, serves consumers via NATS query subjects. |
| **Observation** | Publish contract from insight → memory. A typed, encoded fact — not yet resolved against the graph. See ADR-005. |
| **Retain Job** | Consolidation process inside memory. Receives an Observation, resolves actors → entities, deduplicates, computes schema_fit, detects conflicts, writes entities + relations, updates decay. |
| **Episode** | A task-bounded Claude Code session: intent + start_time + end_time + branch + outcome. Unit of behavioral analysis. |
| **Outcome** | Enum of 8 states for an Episode: `SUCCESS_CLEAN` … `PENDING`. |
| **RC-1..RC-7** | 7 root causes identified for Mickael's recurring behavioral patterns (extracted from manual PR audit #975–#1013, #1036). Defined in `artifacts/specs/spec-roxabi-insight.md`. |
| **Entity** | Node in the memory graph: namespace + slug + type + subtype + memory_strength + decay + compiled_truth reference + … Taxonomy defined in ADR-009 (deferred). |
| **Compiled Truth** | Per-entity markdown document. Regenerated nightly via impact analysis. The human-readable summary of what memory knows about an entity. |
| **Actuation** | The closing loop: memory surfaces patterns → approval queue → auto-PR generator targeting CLAUDE.md / skills / memory entries. |
| **Decay** | Temporal weight function: `weight_temporal = exp(-Δt/σ)`. Old patterns auto-fade; recurring patterns reinforce. Applied during the nightly consolidation pass. |
| **Schema fit** | Float 0..1. How well an incoming Observation fits existing patterns in the graph. `< 0.3` = dark matter (novel, unclassified). `> 0.7` = fast-track (high-confidence consolidation). |

## Common Confusions

| Pair | Distinction |
|---|---|
| Insight vs Memory | Insight = raw + encode (source-aware). Memory = consolidate + serve (graph-aware). Never swap roles. |
| Observation vs Entity | An Observation is an incoming encoded fact (transient). An Entity is a persisted graph node (durable). The Retain Job converts Observations into Entity updates. |
| Episode vs Entity | An Episode is a time-bounded Claude Code session (insight domain). An Entity is a durable graph node in memory (memory domain). Episodes become Observations which update Entity nodes. |
| Compiled Truth vs Observation | Compiled Truth is a nightly-generated summary of all knowledge about one Entity. An Observation is a single incoming fact, before consolidation. |
| Actuation vs Actuation Queue | Actuation = the full mechanism (detect pattern → queue → auto-PR). Approval queue = the pending items awaiting Mickael's approval before the PR is created. |
