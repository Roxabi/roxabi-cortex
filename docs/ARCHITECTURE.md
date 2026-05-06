---
title: Architecture — roxabi-cortex
description: Vue d'ensemble — composants, flux, contracts, storage. Référence à jour ; sources de vérité = ADRs.
status: living
date: 2026-05-06
---

# Architecture — roxabi-cortex

> **Source unique des décisions** = `docs/adr/`. Ce document est une vue d'ensemble lisible qui référence les ADRs. Si conflit entre ce document et un ADR, l'ADR gagne.

## TL;DR

- **roxabi-cortex** = écosystème complet · 2 services (insight + memory) · contracts NATS · producteurs/consommateurs externes
- **insight** = lake + encodage · accueille tout le brut · pipelines ETL par domaine · publie des `Observation` typées
- **memory** = warehouse + consolidation · graphe vivant · decay · compiled truth · assemble · actuate · sert les consommateurs
- Pattern data-eng lake/warehouse (cf. ADR-003)
- Containerisé Podman + Quadlet (cf. ADR-002), repo unique uv workspace (cf. ADR-008)

## Vision

cortex est un **exocortex personnel**. Il capte tout ce qui passe sous les mains de l'utilisateur (sessions Claude Code, conversations Telegram, mails, git, voice, NATS Lyra…), agrège en mémoire structurée (entités + relations avec decay), devient le SSoT cognitif, alimente les agents (Lyra recall, Claude Code `/dev` assemble), et se referme sur lui-même via l'actuation (PRs sur CLAUDE.md / skills / memory).

L'**asset long-terme** = le graphe (dans memory). Le reste (parsers, pipelines, détecteurs, classifiers, reports) est remplaçable.

## Topologie

```
                          Consommateurs (D)
              ┌─ Claude Code ─┐  ┌─ Lyra ──┐  ┌─ Reports ─┐
              │   /dev,       │  │ recall  │  │  weekly   │
              │   assemble    │  │ TG/Disc │  │  digest   │
              └───────┬───────┘  └────┬────┘  └─────┬─────┘
                      │  query NATS    │             │
                      │  roxabi.memory.query.*       │
                      ▼                ▼             ▼
          ┌──────────────────────────────────────────────┐
          │        cortex-memory (warehouse)              │
          │  entités + relations + decay + dedup          │
          │  compiled truth · approval queue              │
          │  assemble · actuate                           │
          │  Retain Job (consolidation Observation→graph) │
          │  DuckDB local (ADR-011)                       │
          │                                               │
          │  NATS subjects:                               │
          │   · roxabi.memory.observations.publish (in)   │
          │   · roxabi.memory.query.* (req/reply)         │
          └──────────────────────▲───────────────────────┘
                                 │ Observation (typée)
                                 │ ADR-005
          ┌──────────────────────┴───────────────────────┐
          │        cortex-insight (lake + ETL)            │
          │  raw event log (toutes sources, lane-tagged)  │
          │  pipelines de traitement par domaine:         │
          │   · behavioral (Claude Code JSONL)            │
          │   · relationship (mail + telegram) — futur    │
          │   · …                                         │
          │  Encodeur: events → Observations typées       │
          │  DuckDB local (ADR-011)                       │
          │                                               │
          │  NATS subjects:                               │
          │   · roxabi.insight.events.publish.{src} (in)  │
          │   · roxabi.insight.fetch.{src} (admin)        │
          └──────────────────────▲───────────────────────┘
                                 │ RawEventEnvelope
                                 │ ADR-004 / ADR-006
          ┌──────────────────────┴───────────────────────┐
          │                Producteurs (A)                │
          │  Claude Code JSONL · git/gh · NATS Lyra ·     │
          │  mail-ingest · telegram-ingest · voice · …    │
          └──────────────────────────────────────────────┘
```

## Composants

### cortex-insight (lake + encodage)

| Module | Rôle |
|---|---|
| `ingest/` | parsers par source (jsonl, mail, telegram, …) · sanitization (trufflehog + regex + entropy) |
| `raw/` | raw event store (DuckDB) · lane-tagged · append-only |
| `pipelines/behavioral/` | Claude Code : segmentation episodes · D1-D15 · outcome classifier |
| `pipelines/relationship/` (futur) | mail + telegram → conversations, topics |
| `encode/` | extraction d'`Observation` typées par catégorie (Interaction, Finding, Decision, Artifact…) |
| `publish/` | NATS publisher → `roxabi.memory.observations.publish` |
| `cli.py` | typer CLI (ingest, detect, classify, report, compare, automation, calibrate) |

### cortex-memory (warehouse + consolidation)

| Module | Rôle |
|---|---|
| `api/` | NATS subscriber (observations) + reply à query subjects |
| `retain/` | Retain Job — consolide `Observation` reçues : actor resolution, dedup, conflict, schema_fit, decay update |
| `graph/` | entities + relations CRUD · decay scheduler · dedup heuristic + cosine |
| `compiled/` | per-entity markdown compiler · impact analysis · regen nightly |
| `assemble/` | DAG-aware context retrieval · bio-aware eviction · goal-conditioned recall |
| `actuate/` | approval queue · auto-PR generator (CLAUDE.md, skill, memory) |
| `nightly/` | consolidation + decay recalc + compiled truth regen |
| `cli.py` | typer CLI (memory entity/compiled/approve/publish, assemble, goal) |

## Flux canoniques

### Claude Code → Insight → Memory

```
1. Session Claude Code écrit ~/.claude/projects/.../abc.jsonl
2. cortex-insight (cocoindex file watcher) ingère
   → sanitize → raw_events table (lane=jsonl)
3. cortex-insight pipeline behavioral
   → segment → episodes
   → D1-D15 detectors → findings
   → outcome classifier (8 états) → episodes.outcome
4. cortex-insight encode
   → produit Observation(category=finding, actors=[detector, episode, project], …)
5. cortex-insight publish
   → roxabi.memory.observations.publish (NATS)
6. cortex-memory subscribe
   → Retain Job consolide :
     · résout actors → entities
     · dedup contre graphe
     · compute schema_fit
     · détecte conflicts
     · update entities + relations
     · update memory_strength + decay
7. cortex-memory nightly
   → compiled_truth régénéré pour entités impactées
8. Claude Code /dev
   → query roxabi.memory.query.assemble (avec goal=issue:N)
   → réponse : contexte assemblé (DAG-aware, bio-eviction)
9. (optionnel) memory.actuate
   → approval queue → auto-PR CLAUDE.md
```

### Mail (futur) → Insight → Memory

```
1. mail-ingest poll IMAP → sanitize PII → publie sur roxabi.insight.events.publish.mail
2. cortex-insight raw_events.lane=mail
3. pipeline relationship → conversation extraction → Observation(category=interaction, actors=[person:anya, self:mickael], topic=…)
4. publish à memory · idem flux Claude Code à partir d'étape 5
```

## Storage

- **insight** : DuckDB embarqué `~/.cortex/insight.duckdb` · workload OLAP/append-heavy
- **memory** : DuckDB embarqué `~/.cortex/memory.duckdb` · workload OLTP/graphe
- **Conditionnel** : memory peut migrer vers KuzuDB si triggers atteints (latence assemble > 200ms · contention writes/reads · > 100k relations) · cf. ADR-011

Schémas détaillés : `docs/insight/DATA-MODEL.md` (à scinder depuis l'actuel `docs/DATA-MODEL.md`) et `docs/memory/DATA-MODEL.md` (à écrire après ADR-009 résolue).

## Contracts

Hébergés dans `roxabi-contracts` (monorepo Lyra : `lyra/packages/roxabi-contracts/`). cf. ADR-006.

| Sous-module | Subjects NATS | Schemas |
|---|---|---|
| `insight.py` | `roxabi.insight.events.publish.{source}` · `roxabi.insight.fetch.{source}` | `RawEventEnvelope` |
| `memory.py` | `roxabi.memory.observations.publish` · `roxabi.memory.query.{entities,assemble,compiled}` · `roxabi.memory.actuate.approve` | `Observation` · `EntityQueryRequest/Response` · `AssembleRequest/Response` |

Distribution : `uv` GitHub source (pattern existant Roxabi).

## Déploiement

Cf. ADR-002. Containerisé Podman + Quadlet, hardening cohérent ADR-053/054 lyra :

| Service | Image | Quadlet unit | Volume | Réseau |
|---|---|---|---|---|
| cortex-insight | `ghcr.io/roxabi/cortex-insight:staging` | `packages/insight/deploy/quadlet/cortex-insight.container` | `%h/.cortex/insight.duckdb` (bind ro/rw) | `roxabi.network` |
| cortex-memory | `ghcr.io/roxabi/cortex-memory:staging` | `packages/memory/deploy/quadlet/cortex-memory.container` | `%h/.cortex/memory.duckdb` | `roxabi.network` |

Ops : `make cortex-insight {start,stop,reload,logs}` · idem memory.

## Repo

```
roxabi-cortex/
├── pyproject.toml                   # uv workspace
├── README.md
├── CLAUDE.md
├── Makefile
├── packages/
│   ├── insight/
│   │   ├── pyproject.toml
│   │   ├── src/cortex_insight/
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   └── deploy/quadlet/
│   └── memory/
│       ├── pyproject.toml
│       ├── src/cortex_memory/
│       ├── tests/
│       ├── Dockerfile
│       └── deploy/quadlet/
├── docs/
│   ├── ARCHITECTURE.md              # ce document
│   ├── adr/                          # decision log
│   ├── insight/{DATA-MODEL,DETECTORS}.md
│   └── memory/DATA-MODEL.md
└── artifacts/
    ├── specs/                        # spec-cortex-{insight,memory}.md
    ├── plans/
    ├── frames/
    └── analyses/
```

cf. ADR-008.

## Décisions (index)

Voir `docs/adr/README.md` pour l'index complet. Décisions structurantes :

| ADR | Sujet | Statut |
|---|---|---|
| ADR-001 | Naming roxabi-cortex | accepted |
| ADR-002 | Podman + Quadlet | accepted |
| ADR-003 | Lake / warehouse split | accepted |
| ADR-004 | Producteurs → insight | accepted |
| ADR-005 | Encode vs consolide · contrat `Observation` | accepted |
| ADR-006 | Contracts package extension | accepted |
| ADR-007 | Mode arrivée par source (push/pull/hook) | open |
| ADR-008 | Repo unique workspace | accepted |
| ADR-009 | Taxonomie entités (biomimétisme) | deferred |
| ADR-010 | Cohabitation Lyra | deferred |
| ADR-011 | Storage DuckDB v1 · revisit conditionnel | accepted-conditional |

## Statut implémentation

**Design phase finalisée. Implémentation pas commencée.**

Bloquants identifiés avant implémentation :

- ADR-009 (taxonomie) à régler — bloque DATA-MODEL memory
- Spec actuel `artifacts/specs/spec-roxabi-insight.md` à scinder en `spec-cortex-insight.md` + `spec-cortex-memory.md`
- Repo à renommer `roxabi-insight` → `roxabi-cortex`
- Contracts à étendre dans `lyra/packages/roxabi-contracts/`

Non-bloquants (peuvent être traités en parallèle ou en Phase 2+) :

- ADR-007 (mode arrivée) — par source, à l'implémentation
- ADR-010 (Lyra cohabitation) — Phase 2+
- Phasing détaillé (insight/memory v1 → v2 LLM → v3 actuation → v4 GEPA)
