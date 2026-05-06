---
adr: ADR-011
title: Storage — DuckDB v1 partout · revisit memory si triggers
status: accepted-conditional
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-003]
tags: [storage, duckdb, kuzu, technology, to-discuss]
---

## Contexte

Le choix initial DuckDB a été figé dans `docs/DATA-MODEL.md` (Q13) sous le mindset « observability tool » : ingest one-shot batch + reports périodiques sur 5,657 fichiers JSONL. Le rationnel :

| Argument | Pertinent quand le projet était… | Pertinent maintenant ? |
|---|---|---|
| Workload analytique (agrégations cross-source) | observability tool batch | partiellement vrai pour insight, ¬ pour memory |
| Native Parquet (export stages intermédiaires) | reproductibilité pipeline behavioral | encore vrai pour insight |
| Single-file portable, ¬serveur | déploiement simple | encore vrai des deux côtés |
| Concurrence one-shot batch + reads-only | hypothèse « ingest = job batch » | **¬ vrai** : daemon en service, writes streaming continus |
| Cross-source joins columnar-friendly | jointures Tx + git + GitHub | encore vrai dans insight |

Avec le pivot cortex (deux services daemon, charges différentes), le choix doit être revisité par service.

## Charges réelles par service

| Service | Pattern dominant | Type DB qui colle naturellement |
|---|---|---|
| **insight (lake)** | append-heavy raw events · ETL pipelines · scans larges · cross-source joins · export possible Parquet | OLAP columnar — DuckDB juste |
| **memory (warehouse)** | lookup entité par slug · voisinage `relations WHERE source=X OR target=X` · graph traversal récursif · decay batch update · assemble DAG · 1-100 req/s reads par consommateurs | OLTP / graphe — DuckDB sous-optimal |

## Décision

**v1 : DuckDB partout** (insight et memory).

**Triggers de revisit pour memory** (si l'un atteint en mesure réelle) :

| Trigger | Seuil |
|---|---|
| Latence `assemble` p95 | > 200 ms sustained |
| Contention writes vs reads sur memory | observée (lock contention, retry budget dépassé) |
| Volume relations | > 100 000 |
| Volume entités | > 10 000 |

**Cible si trigger atteint** : KuzuDB (graphe natif embarqué, single-file, Cypher, perf reconnue, esprit DuckDB). Migration estimée tractable car le schéma graphe est versionné et les données sont régénérables depuis raw events.

## Conséquences

| Aspect | Impact |
|---|---|
| v1 implémentation | uniformité techno · 1 seul moteur à apprendre · friction minimale |
| Mesure obligatoire | nécessite d'instrumenter memory dès v1 (latence assemble, lock waits) — sinon les triggers sont inopérants |
| Pas de lock-in fort | les schémas sont en SQL standard · les contraintes graphe sont en logique applicative (pas en triggers DB) · migration vers Cypher tractable |
| Documentation | DATA-MODEL.md memory doit indiquer cette décision conditionnelle pour préserver le rationnel |

## Alternatives évaluées

| Option | Pour | Contre | Verdict |
|---|---|---|---|
| **DuckDB partout** | uniformité, pas de nouvelle techno, volumes v1 < seuils critiques | column store ¬ idéal pour lookup point · concurrence single writer · graph traversal verbeux via recursive CTE | **CHOISI v1** |
| SQLite + WAL | OLTP mature, single-file, concurrence WAL OK | ¬ graphe natif, ¬ Parquet, pas de support analytique large | rejeté — perd les bénéfices DuckDB pour insight, n'apporte rien pour memory |
| KuzuDB | graphe natif embarqué · Cypher · single-file · perf bonne | techno récente · à apprendre · écosystème + petit · doublon avec DuckDB | **CIBLE conditionnelle pour memory** si triggers |
| Postgres + Apache AGE | mature, Cypher via AGE, multi-process | service séparé · plus lourd Quadlet · contrarie « 1 service = 1 DB locale » | rejeté — friction infra trop grande pour le bénéfice |
| Neo4j | graphe natif établi | service séparé · licensing communautaire vs entreprise · stack JVM | rejeté — overkill et hors stack |

## Approfondissement — angles à discuter (en attente)

Cet ADR est `accepted-conditional` : la décision pour v1 (DuckDB partout) tient, mais le rationnel et les triggers méritent d'être creusés avant de figer durablement. **Approfondissement déféré · à reprendre comme session dédiée.**

### Angles identifiés

| # | Angle | Question centrale |
|---|---|---|
| 1 | **Concurrence DuckDB en daemon long-running** | Modèle exact (single-writer multi-reader, MVCC, lock waits sous charge) ? Tenue avec writes streaming continus + reads en parallèle ? Versions ≥1.0 ont-elles résolu les limitations historiques ? |
| 2 | **Graph workload sur DuckDB** | Recursive CTE en pratique : perf de l'assemble DAG-aware, lisibilité du SQL, scaling avec voisinage dense. Alternative : index voisinage pré-calculé en table dédiée ? |
| 3 | **KuzuDB maturité 2026** | Production-readiness · qui l'utilise en prod · gouvernance projet · vélocité release · stabilité API · écosystème (drivers Python, intégration BI, etc.) |
| 4 | **Migration path DuckDB → KuzuDB** | Coût réel si trigger atteint : schéma équivalent en Cypher · outillage de transfert · downtime · re-build du graphe depuis raw events. Estimation : semaines vs mois. |
| 5 | **Embedded vector store** | Pertinent pour schema_fit / conflict detection si on veut du semantic match. Options : DuckDB `vss` extension · KuzuDB vector capabilities · ne rien faire (heuristique IDF-Jaccard suffit). Orthogonal au choix DB principal. |

### Recommandé pour la session d'approfondissement

**1 + 3 + 4 groupés** — c'est le triplet qui décide réellement si on locks DuckDB ou si on garde KuzuDB en cible crédible.

| Angle | Pourquoi maintenant |
|---|---|
| 1 (concurrence DuckDB) | si DuckDB tient en charge daemon, le trigger « contention writes/reads » devient peu probable → KuzuDB cible théorique seulement |
| 3 (KuzuDB maturité) | si KuzuDB est risquée en prod 2026, on ne devrait pas la garder en cible crédible, et on doit identifier une autre alternative |
| 4 (migration path) | conditionne la formulation des triggers : si migration coûte 6 mois, les triggers doivent être conservateurs ; si 2 semaines, on peut migrer plus tôt |

**(2)** testable plus tard avec mesures réelles sur graphe naissant. **(5)** orthogonal · à traiter dans un ADR vector-store séparé, après ADR-009 (taxonomie) qui pourra dire si schema_fit a vraiment besoin de semantic.

### Output attendu

Note d'analyse `artifacts/analyses/storage-deep-dive-YYYY-MM-DD.md` · si la conclusion change la décision actuelle → ADR-NNN nouvelle qui supersedes celle-ci.

### Bloquants pour reprendre

Aucun · à programmer dès que Mickael décide que le sujet redevient priorité (probablement avant d'écrire la première ligne de `cortex_memory.graph`).

## Re-evaluation

| Quand | Quoi |
|---|---|
| Phase 1 implémentation memory | instrumenter latence + lock waits dès le début |
| À chaque trigger atteint | revisit · si KuzuDB validée → ADR-NNN nouvelle qui supersedes celle-ci |
| Périodiquement (chaque 6 mois) | revue des chiffres · pas changer si pas trigger · pas changer pour le plaisir |
