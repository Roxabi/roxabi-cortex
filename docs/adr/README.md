---
title: Decision Log — roxabi-cortex
description: Index des Architecture Decision Records (ADRs) du projet
---

# Decision Log — roxabi-cortex

ADRs cadrant l'architecture, le découpage, les choix technos et les conventions du projet `roxabi-cortex`.

## Statuts

| Statut | Signification |
|---|---|
| `accepted` | décision prise, en vigueur |
| `accepted-conditional` | prise mais avec triggers de revisit explicites |
| `proposed` | proposition ouverte à discussion |
| `open` | question identifiée, décision déférée par source/cas |
| `deferred` | décision déférée à une étape ultérieure (bloqueurs identifiés) |
| `superseded` | remplacée par un ADR plus récent (voir `superseded_by`) |
| `rejected` | proposition explicitement rejetée |

## Index

| ADR | Titre | Statut | Tags |
|---|---|---|---|
| [ADR-001](ADR-001-naming-roxabi-cortex.md) | Nommage de l'écosystème — roxabi-cortex | `accepted` | naming, scope |
| [ADR-002](ADR-002-deployment-podman-quadlet.md) | Déploiement — Podman + Quadlet | `accepted` | deployment, infra |
| [ADR-003](ADR-003-lake-warehouse-split.md) | Découpage lake (insight) / warehouse (memory) | `accepted` | architecture, separation |
| [ADR-004](ADR-004-producers-publish-to-insight.md) | Producteurs externes → insight | `accepted` | architecture, ingestion |
| [ADR-005](ADR-005-encode-vs-consolidate-observation-contract.md) | Encode (insight) vs consolide (memory) — contrat `Observation` | `accepted` | architecture, contract |
| [ADR-006](ADR-006-contracts-package-extension.md) | Extension de roxabi-contracts (insight + memory) | `accepted` | contracts, nats |
| [ADR-007](ADR-007-source-arrival-mode.md) | Mode d'arrivée du brut (push/pull/hook) | `open` | ingestion, deferred-per-source |
| [ADR-008](ADR-008-monorepo-workspace.md) | Repo unique `roxabi-cortex` · uv workspace | `accepted` | packaging, repo-structure |
| [ADR-009](ADR-009-entity-taxonomy.md) | Taxonomie des entités (biomimétisme) | `deferred` | taxonomy, ontology |
| [ADR-010](ADR-010-lyra-cohabitation.md) | Cohabitation Lyra ↔ cortex | `deferred` | lyra, integration |
| [ADR-011](ADR-011-storage-duckdb-v1.md) | Storage — DuckDB v1 · revisit si triggers | `accepted-conditional` | storage, duckdb, kuzu |

## Convention

- Numérotation séquentielle (`ADR-NNN`), 3 digits, jamais réutilisée même si rejetée
- Frontmatter YAML obligatoire (status, date, deciders, related, tags)
- Sections fixes : Contexte · Décision · Conséquences · Alternatives écartées · Notes
- Pour `open` / `deferred` : Statut · Question/Pistes · Bloquants · Re-evaluation
- Un ADR superseded n'est jamais supprimé — sa frontmatter reçoit `superseded_by: ADR-XXX`

## Comment écrire un nouvel ADR

1. Identifier la décision à formaliser (architecture, choix techno, convention)
2. Choisir le prochain numéro disponible (regarder l'ADR le plus haut)
3. Créer `ADR-NNN-slug.md` avec le frontmatter et les sections
4. Ajouter une ligne dans l'index ci-dessus
5. Si supersedes un ADR existant, marquer l'ancien `superseded` + `superseded_by: ADR-NNN`

## Pour les agents Claude Code

- Avant toute décision architecturale, lire les ADRs `accepted` pertinents
- Avant de proposer une alternative à un choix existant, lire l'ADR correspondant et son raisonnement (alternatives écartées)
- Si un ADR est `deferred` et que la décision arrive, écrire le suivant qui le supersede
- Ne jamais éditer un ADR `accepted` à la légère — créer un nouvel ADR qui le supersede
