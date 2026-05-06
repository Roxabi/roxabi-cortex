---
title: Issue Management
description: GitHub Project V2, status flow, labels, sizing, and ADR-driven backlog for roxabi-cortex.
---

# Issue Management

> Universal patterns (severity × impact matrix, spec completeness) are embedded in the `product-lead` agent.
> This file documents **cortex-specific** issue conventions.

## Board

GitHub Project V2 — board #26 at [https://github.com/orgs/Roxabi/projects/26](https://github.com/orgs/Roxabi/projects/26).

## Issue Lifecycle

```
Backlog → Analysis → Specs → In Progress → Review → Done
```

| Status | Meaning |
|---|---|
| Backlog | Identified, not yet started. ADR-driven design issues stay here until the ADR is resolved. |
| Analysis | Being analyzed — frame / research / ADR write in progress. |
| Specs | Spec being written (`artifacts/specs/{issue}-{slug}.md`). |
| In Progress | Implementation in worktree. |
| Review | PR open, awaiting merge. |
| Done | Merged and verified. |

## Sizing

Sizes map to the tier model:

| Size | Tier | Scope |
|---|---|---|
| S | S | ≤ 3 files, single domain, no unknowns |
| F-lite | F-lite | Clear scope, 4–10 files, single domain |
| F-full | F-full | Multi-domain, new architecture, unknowns |

## Priority

| Priority | Meaning |
|---|---|
| P0 | Blocker — stops other work |
| P1 | High — current sprint |
| P2 | Normal — next sprint |
| P3 | Low — backlog / nice to have |

## Labels

11 labels (org-level):

| Label | When |
|---|---|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `refactor` | Code restructure without behavior change |
| `docs` | Documentation only |
| `test` | Tests only |
| `chore` | Maintenance, deps, tooling |
| `ci` | CI/CD changes |
| `perf` | Performance improvement |
| `epic` | Parent issue grouping related work |
| `research` | Investigation, ADR prep, analysis |
| `blocked` | Waiting on another issue or external decision |

## Issue Types (org-level)

`feat` · `fix` · `refactor` · `docs` · `test` · `chore` · `ci` · `perf` · `epic` · `research`

## ADR-Driven Issues

Design-phase issues that depend on an unresolved ADR stay in **Backlog** with `blocked` label. Example:

- Issue #3 (extend roxabi-contracts) — `blocked` by issue #2 (ADR-009 entity taxonomy)

Once the blocking ADR is resolved, the issue moves to Analysis.

## Current Blockers (2026-05-06)

| Issue | ADR | Blocker |
|---|---|---|
| #3 — extend roxabi-contracts | ADR-006 | blocked-by #2 (ADR-009 entity taxonomy deferred) |
| #2 — entity taxonomy | ADR-009 | deferred — biomimetic interview needed |

## Templates

> TODO: Add GitHub issue templates once implementation begins. Suggested: `feat` (problem + proposed solution + ADR ref), `fix` (symptom + reproduction + expected), `research` (question + options + output artifact path).

## AI Quick Reference

- ALWAYS check board #26 before starting work on an issue — verify it's not blocked.
- NEVER start implementation of an ADR-driven issue while the governing ADR is `deferred` or `open`.
- ALWAYS link `blocked` issues to their blocking issue number in the issue body.
