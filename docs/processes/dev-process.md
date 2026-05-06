---
title: Development Process
description: /dev pipeline, tier model, worktree rules, and release conventions for roxabi-cortex.
---

# Development Process

All work flows through `/dev #N`. Full behavioral rules in `~/.claude/shared/global-patterns.md`.

## Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | stable (merge-commit only, no squash) |
| `<issue#>-slug` | feature/fix branch when a GitHub issue exists (e.g. `3-extend-contracts`) |
| `descriptive-slug` | branch without an issue (e.g. `scaffold-quadlet-units`) |

No `staging` branch — single-host project, no staging environment promotion.

## Tier Model

| Tier | Trigger | Worktree |
|---|---|:---:|
| S | ≤ 3 files, single domain, no unknowns | Optional |
| F-lite | Clear scope, 4–10 files | Mandatory |
| F-full | Multi-domain, new architecture, unknowns | Mandatory |

Tier is determined by the `/dev` skill — do not reclassify manually.

## Workflow

```
/dev #N
  │
  ├─ S      → impl directly → PR → merge to main
  │
  ├─ F-lite → frame → spec → plan → impl (worktree) → verify → PR → merge
  │
  └─ F-full → frame → analyze → spec → plan → impl (worktree) → verify → PR → merge
```

Artifacts land in:

| Artifact | Path |
|---|---|
| Frames | `artifacts/frames/` |
| Analyses | `artifacts/analyses/` |
| Specs | `artifacts/specs/{issue}-{slug}.md` |
| Plans | `artifacts/plans/` |

## ADR Gate

Before any implementation that touches storage, deployment, contracts, or service boundaries:

1. Read the governing ADR(s) from [docs/adr/README.md](../adr/README.md).
2. If the decision is not yet made → propose DP(A) to Mickael, do not decide unilaterally.
3. If deciding something new during work → write the ADR before implementing.
4. Never edit an `accepted` ADR — create a new one that supersedes it.

## Code Ownership

Solo project. All paths owned by Mickael. Agents submit PRs; Mickael merges.

| Path | Domain |
|---|---|
| `packages/insight/` | cortex-insight (lake + ETL) |
| `packages/memory/` | cortex-memory (warehouse + graph) |
| `docs/adr/` | Architecture decisions (immutable once accepted) |
| `.github/` | CI/CD (devops domain) |

## Release Process

Tags follow `<component>/vX.Y.Z` convention (per `~/projects/CLAUDE.md`):

```
cortex-insight/v0.1.0
cortex-memory/v0.1.0
```

PRs: merge-commit only (no squash). Releases are tagged on `main` after merge.

## CI

`.github/workflows/pr-title.yml` enforces Conventional Commit format on PR titles. Pre-commit hooks run ruff + pyright.

## AI Quick Reference

- ALWAYS use `/dev #N` as the entry point — never start implementation without a tier determination.
- NEVER code on `main` without a worktree for F-lite or F-full tiers.
- ALWAYS write an ADR before implementing an architectural decision that doesn't have one.
- PREFER `<issue#>-slug` branch naming when a GitHub issue exists.
