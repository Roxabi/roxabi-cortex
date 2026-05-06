---
adr: ADR-007
title: Mode d'arrivée du brut côté insight (push / pull / hook)
status: open
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-004]
tags: [ingestion, sources, deferred-per-source]
---

## Contexte

Plusieurs sources doivent alimenter cortex-insight (cf. ADR-004). Chacune a ses propres caractéristiques de disponibilité et de découverte d'événements.

Trois modes possibles :

| Mode | Description | Exemples naturels |
|---|---|---|
| **push** | la source publie spontanément à insight (NATS subject) | NATS Lyra · webhooks externes |
| **pull** | insight va chercher la donnée à intervalles | mails IMAP · APIs REST avec polling · git/gh log |
| **hook** | un événement filesystem ou autre déclenche notification → insight pull/parse | Claude Code JSONL (file watch via cocoindex) · inotify sur dossier |

## Statut : open

Décision déférée — à arbitrer **source par source** au moment de l'implémentation.

## Pistes par source connue

| Source | Mode probable | Notes |
|---|---|---|
| Claude Code JSONL | hook (file watch via cocoindex) | les fichiers JSONL apparaissent dans `~/.claude/projects/` à mesure des sessions |
| git/gh | pull (`git log`, `gh` API périodique) | pas de webhook configuré ; polling acceptable |
| NATS Lyra (`lyra.*`) | push (subscribe direct) | bus déjà actif, latence minimale |
| mail IMAP | pull (poll IDLE ou intervalle) | IMAP IDLE recommandé pour quasi-temps-réel |
| Telegram (direct) | push (webhook bot) ou pull (long polling) | dépend si on a un bot dédié ou si on consomme via Lyra |
| voice (transcripts) | hook (file watch sur sortie STT) ou push (NATS) | dépend du pipeline voice |

## Bloquants pour décision finale

- Volume réel par source (drives push vs pull tradeoffs)
- Latence requise par cas d'usage (recall live vs digest hebdo)
- Disponibilité d'API webhook chez les sources externes

## Conséquences (anticipées)

Insight doit **supporter les trois modes** — pas un seul. Côté implémentation :

- un subscriber NATS générique (push)
- un poller paramétrable par source (pull)
- un file watcher (hook)

Chaque source = une config TOML qui choisit son mode. Pas de mode imposé par insight.

## Re-evaluation

Cet ADR sera scindé en N décisions, une par source, au moment de l'implémentation de chaque pipeline d'ingestion. Cet ADR-007 reste comme cadre de référence et devient `superseded_by` les ADRs futurs (ADR-NNN-arrival-mode-{source}).
