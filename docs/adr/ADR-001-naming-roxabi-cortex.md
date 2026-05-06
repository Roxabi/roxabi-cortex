---
adr: ADR-001
title: Nommage de l'écosystème — roxabi-cortex
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-003, ADR-005, ADR-008]
tags: [naming, scope, identity]
---

## Contexte

Le repo a démarré sous le nom `roxabi-insight` avec un scope étroit : « behavioral observability for Claude Code transcripts ». Le scope a depuis absorbé :

- la mémoire générale (4-layer Raw → Graph → Compiled Truth → Actuation)
- l'ingestion multi-source (NATS Lyra existant ; mails/Telegram à venir)
- l'actuation (CLAUDE.md / skills / memory PRs)

Conséquence : identité diffuse, README dissone avec spec, pas de nom pour l'ensemble.

## Décision

Le **nom de l'écosystème complet** = `roxabi-cortex`.

L'écosystème comprend :

| Composant | Rôle |
|---|---|
| `cortex_insight` (service) | « lake + encodage » — raw events multi-source + pipelines ETL + production d'observations typées |
| `cortex_memory` (service) | « warehouse + consolidation » — graphe vivant + decay + compiled truth + assemble + actuate |
| Producteurs externes | Claude Code JSONL · git/gh · NATS Lyra · mails · Telegram · voice · … |
| Consommateurs | Lyra agent · Claude Code `/dev` · reports · dashboards |

Le repo Git est renommé : `roxabi-insight` → `roxabi-cortex`.

## Conséquences

| Acteur | Impact |
|---|---|
| Repo Git | renommage `roxabi-insight` → `roxabi-cortex` (move ou nouveau repo + import) |
| Workspace | 2 packages : `packages/insight` + `packages/memory` (cf. ADR-008) |
| Vocabulaire | « cortex » = ensemble · « insight » / « memory » = services internes · jamais ambigu |
| Documentation | l'intégralité du contenu actuel doit être ré-alignée |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| Garder `roxabi-insight` pour l'ensemble | conflit avec le sous-service `insight` · nom historiquement étroit · perpétue la confusion |
| `roxabi-cognition` | trop philosophique · plus abstrait que nécessaire |
| `roxabi-mind` | sous-entend conscience/intentionnalité · trop large |
| `roxabi-brain` | familier mais moins précis que cortex |

## Notes

Le naming biologique `cortex` est cohérent avec le modèle bio-inspiré déjà adopté (hippo-memory, decay, consolidation nightly). Voir ADR-005 pour l'analogie hippocampe/cortex sémantique appliquée à la frontière insight/memory.
