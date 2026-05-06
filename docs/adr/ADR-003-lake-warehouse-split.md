---
adr: ADR-003
title: Découpage lake (insight) / warehouse (memory)
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-001, ADR-004, ADR-005, ADR-008]
tags: [architecture, separation-of-concerns, data-eng]
---

## Contexte

Le projet roxabi-insight initial fusionnait trois systèmes dans un seul repo :

1. **Behavioral observability** Claude Code (D1-D15, outcome classifier, RC mapping)
2. **Memory layer** générique (entités + relations + decay + compiled truth + actuation), absorbé du design lyra-memory (« one project, not two »)
3. **Ingestion multi-lane** (JSONL + git/gh + NATS, plus mails/Telegram à venir)

Conséquences observées dans la spec :

- Le schéma `events` est JSONL-centric (`tool_name`, `tool_args_hash`, `error_flag`, …). Inutilisable tel quel pour mails/Telegram.
- Le Retain Job vit avec les détecteurs Claude Code → couple le graphe à un domaine spécifique.
- Le graphe — l'asset long-terme — vit dans le repo de l'analyseur. Inversé.
- Identité du repo diffuse : « observability tool » dans le README, « memory + observability platform » dans la spec.

La question : faut-il scinder ? Si oui, comment ?

## Décision

Découpage **lake / warehouse** (pattern data-engineering classique, bien établi) :

| Service | Rôle | Évolution |
|---|---|---|
| **cortex-insight (lake)** | accueille tout le brut multi-source · stocke raw events · pipelines ETL par domaine · produit des observations typées | rapide — nouveaux parsers, nouveaux pipelines, GEPA, LLM Phase 2 |
| **cortex-memory (warehouse)** | reçoit les observations · consolide en graphe (entités + relations) · decay · dedup · conflict · compiled truth · assemble · actuate · sert les consommateurs | lente — schéma graphe versionné · API stable |

Frontière nette : **insight ne stocke pas le graphe ; memory ne parse pas le brut**.

## Conséquences

| Aspect | Impact |
|---|---|
| Stabilité | memory devient l'asset long-terme protégé · insight peut être réécrit sans toucher à la connaissance accumulée |
| Schéma | events bruts dans insight = source-spécifique (tagué par lane) · graphe dans memory = générique |
| Dépendances | insight = lourd (parsers, regex, LLM, NATS, polars, cocoindex…) · memory = minimal (DuckDB/KuzuDB, NATS) |
| Producteurs | publishent à insight uniquement (cf. ADR-004) |
| Consommateurs | querient memory uniquement |
| Évolutivité | ajouter une source = nouveau pipeline insight · zéro touche à memory |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| Tout dans un seul repo `roxabi-insight` (statu quo) | les 3 problèmes ci-dessus persistent · scope confus · contamine le schéma graphe |
| Renommer + redocumenter sans split conceptuel | ne résout aucun problème de fond |
| Split en 3 (sources / extraction / store) | sur-découpé pour solo dev · le couplage entre extraction et raw justifie de les co-localiser dans insight |

## Notes

Le pattern lake/warehouse est éprouvé en data-eng (Snowflake, Databricks, dbt…). Il sépare « stocker tout brut au cas où » (lake, append-heavy, schema-on-read) de « modèle propre pour l'usage » (warehouse, schema-on-write, consommateurs). Notre adaptation est mono-host et embarquée, mais le découpage logique est le même.

La question packaging (1 repo monorepo vs 2 repos séparés) est tranchée séparément dans ADR-008.
