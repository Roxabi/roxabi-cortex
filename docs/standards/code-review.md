---
title: Code Review Standards
description: Review checklist, blocking criteria, and ADR-adherence gate for roxabi-cortex.
---

# Code Review Standards

> Universal patterns (security checklist, severity definitions) are embedded in the `security-auditor` agent.
> This file documents **cortex-specific** review criteria.

## Review Checklist

- [ ] Follows service boundary: insight NEVER imports memory, memory NEVER imports insight ([ADR-008](../adr/ADR-008-monorepo-workspace.md))
- [ ] NATS subjects imported from `roxabi_contracts` (NEVER hardcoded)
- [ ] New source parser goes in `cortex_insight.ingest.*` — not in memory
- [ ] Retain Job logic goes in `cortex_memory.retain.*` — not in insight
- [ ] Raw events pass through sanitization pipeline before storage
- [ ] DuckDB access: single connection per service, writes only from owning service
- [ ] ADR adherence: any storage, deployment, or architecture change references the relevant ADR
- [ ] Tests added/updated for all changed behavior
- [ ] No secrets or nkeys hardcoded or committed
- [ ] File ≤ 300 lines, folder ≤ 12 files (quality gates in `stack.yml`)
- [ ] pyright strict: no untyped `Any` without explicit comment justification
- [ ] No TODO without a linked issue number

## Conventional Comments

| Label | Blocks merge? | When |
|---|:---:|---|
| `issue(blocking):` | Yes | Bug, security violation, spec violation |
| `suggestion(blocking):` | Yes | Service boundary violation, standards violation, ADR divergence |
| `suggestion(non-blocking):` | No | Improvement, refactor idea |
| `nitpick:` | No | Style preference, minor naming |
| `praise:` | No | Good pattern worth noting |

## Blocking Conditions

A PR **must not merge** if any of the following apply:

| Condition | Why |
|---|---|
| Cross-package import (`cortex_insight` ↔ `cortex_memory`) | Violates ADR-003 / ADR-008 boundary |
| Hardcoded NATS subject string | Breaks contract SSoT (ADR-006) |
| Unsanitized raw data written to DuckDB | Security / privacy |
| New architectural decision made in code without ADR | ADR-first rule (CLAUDE.md) |
| Podman secrets replaced with plaintext env vars | Security (ADR-002) |
| KuzuDB introduced without a superseding ADR-011 | ADR-conditional (ADR-011) |

## ADR Adherence Gate

For any PR touching storage, deployment, contracts, or service boundaries:

1. Identify the governing ADR(s) from [docs/adr/README.md](../adr/README.md).
2. Verify the change is consistent with the ADR decision and its accepted alternatives.
3. If the change diverges → flag `suggestion(blocking):` with the ADR number and rationale.
4. If a new decision is made → require an ADR before merging.

## AI Quick Reference

- ALWAYS check the service boundary (cross-package import = blocking).
- NEVER approve a PR that hardcodes NATS subjects or introduces KuzuDB without a superseding ADR.
- ALWAYS verify architectural changes against the relevant accepted ADR before approving.
