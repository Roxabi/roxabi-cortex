---
adr: ADR-008
title: Repo unique `roxabi-cortex` · uv workspace · packages/{insight,memory}
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-001, ADR-003]
tags: [packaging, repo-structure, workspace]
---

## Contexte

ADR-003 fixe le découpage logique lake (insight) / warehouse (memory). Reste à choisir le **packaging physique** :

| Option | Description |
|---|---|
| a. 2 repos séparés | `roxabi-insight/` + `roxabi-memory/` · release lines indépendantes |
| b. 1 repo monorepo workspace | `roxabi-cortex/` avec `packages/insight/` + `packages/memory/` · uv workspace · 1 release line |
| c. Tout fusionné en 1 package | un seul `roxabi-cortex/src/cortex/` avec sub-modules |

## Décision

**Option b — 1 repo monorepo workspace.**

```
roxabi-cortex/
├── pyproject.toml                   # uv workspace racine (members = packages/*)
├── README.md
├── CLAUDE.md
├── Makefile
├── packages/
│   ├── insight/
│   │   ├── pyproject.toml           # cortex-insight
│   │   ├── src/cortex_insight/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── deploy/quadlet/cortex-insight.container
│   └── memory/
│       ├── pyproject.toml           # cortex-memory
│       ├── src/cortex_memory/
│       ├── tests/
│       ├── Dockerfile
│       └── deploy/quadlet/cortex-memory.container
├── docs/
│   ├── ARCHITECTURE.md
│   ├── adr/                          # ADRs (ce dossier)
│   ├── insight/DATA-MODEL.md
│   ├── insight/DETECTORS.md
│   └── memory/DATA-MODEL.md
└── artifacts/
    ├── specs/                        # spec-cortex-insight.md, spec-cortex-memory.md
    ├── plans/
    ├── frames/
    └── analyses/
```

### Discipline interne

| Règle | Mécanisme |
|---|---|
| `cortex_insight.*` ne peut pas importer `cortex_memory.*` | pas dépendance dans `packages/insight/pyproject.toml` |
| `cortex_memory.*` ne peut pas importer `cortex_insight.*` | idem côté memory |
| Communication exclusive via `roxabi-contracts.{insight,memory}` sur NATS | les deux packages dépendent de `roxabi-contracts` |
| Tests inter-package = tests d'intégration end-to-end | montent les deux containers + NATS local |

## Conséquences

| Aspect | Impact |
|---|---|
| Friction quotidienne | 1 release line, 1 set de CI, 1 endroit à clone — moins de friction solo dev |
| Couplage interne | discipline imposée par les pyproject (pas d'import cross-package) — frontière physique mais reproduit dans la structure |
| Évolution | si un consommateur tiers veut consommer memory sans insight → split repo possible plus tard (option a) sans douleur (les contrats existent déjà) |
| Containerisation | 1 Dockerfile par package · images séparées sur GHCR · aligné avec ADR-002 |
| Dev local | `uv sync` à la racine sync les deux packages d'un coup |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| a. 2 repos séparés | friction quotidienne (cross-repo PRs · 2 CIs · 2 sets de versions) inutile en solo dev · le couplage logique est fort, le couplage physique n'apporte pas de bénéfice tangible |
| c. Package unique fusionné | perd la frontière insight/memory · contredit ADR-003 |

## Notes

Le renommage du repo `roxabi-insight` → `roxabi-cortex` est une étape liée à cet ADR mais peut être faite séparément. L'option `git mv` in-place préserve l'historique. Voir issue de migration séparément.

Si jamais un consommateur externe (autre projet, équipe externe) veut utiliser cortex-memory sans cortex-insight, le split en 2 repos devient justifié — c'est le **trigger** de re-évaluation de cet ADR.
