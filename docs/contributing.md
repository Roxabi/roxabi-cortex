---
title: Contributing
description: Branch naming, commit conventions, PR rules, and ADR discipline for roxabi-cortex.
---

# Contributing

## Getting Started

```bash
# Clone and sync dependencies
git clone git@github.com:Roxabi/roxabi-cortex.git ~/projects/roxabi-cortex
cd ~/projects/roxabi-cortex
uv sync

# Verify both CLIs are available
uv run cortex-insight --help
uv run cortex-memory --help

# Run tests
uv run pytest

# Lint + format
uv run ruff check
uv run ruff format

# Type check
uv run pyright
```

No `.env.example` yet — see [Configuration](standards/configuration.md) for required variables.

## Branch Naming

| Case | Format | Example |
|---|---|---|
| Issue exists | `<issue#>-slug` | `3-extend-contracts` |
| No issue | descriptive kebab-case | `scaffold-quadlet-units` |

Always branch from `main`.

## Commit Conventions

Format: `<type>(<scope>): <description>`

| Type | When |
|---|---|
| `feat` | New capability |
| `fix` | Bug fix |
| `refactor` | Restructure without behavior change |
| `docs` | Documentation only |
| `test` | Tests only |
| `chore` | Maintenance, deps, tooling |
| `ci` | CI/CD changes |
| `perf` | Performance improvement |

Scope examples: `insight`, `memory`, `contracts`, `quadlet`, `adr`, `deps`.

Example: `feat(insight): add JSONL cocoindex file watcher`

Enforced on PR titles via `.github/workflows/pr-title.yml`.

## Pull Requests

- Target: `main` (no staging branch)
- Merge strategy: **merge-commit only** (no squash, no rebase) — per `~/projects/CLAUDE.md`
- PR title must follow Conventional Commits format
- Link the issue in the PR body (`Closes #N`)
- All CI checks must pass before merge

## Architecture Decisions

Before implementing anything that touches storage, deployment, contracts, or service boundaries:

1. Read the relevant accepted ADR(s) in [docs/adr/](adr/README.md).
2. If no ADR covers the decision → write one before implementing (use the next available number).
3. If proposing an alternative to an existing accepted decision → read the ADR's "Alternatives écartées" section first.
4. **Never edit an accepted ADR** — create a new ADR that supersedes it.

ADR convention: `ADR-NNN-slug.md` · YAML frontmatter (`status`, `date`, `deciders`, `related`, `tags`) · fixed sections (Contexte · Décision · Conséquences · Alternatives écartées · Notes).

## Documentation

- Docs live in `docs/` as plain Markdown (`.md`).
- Update relevant docs when changing public behavior, CLI commands, NATS subjects, or config options.
- No nav files needed (plain markdown, no framework).
- ADRs: add a row to `docs/adr/README.md` when creating a new ADR.

## Quality Gates

Enforced via pre-commit hooks and CI:

| Gate | Tool | Config |
|---|---|---|
| Lint | ruff check | `pyproject.toml` |
| Format | ruff format | `pyproject.toml` |
| Type check | pyright (strict) | `pyproject.toml` |
| Tests | pytest | `packages/*/tests/` |
| File length | max 300 lines | `stack.yml` quality_gates |
| Folder size | max 12 files | `stack.yml` quality_gates |

Run all gates: `uv run ruff check && uv run ruff format && uv run pyright && uv run pytest`
