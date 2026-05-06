---
adr: ADR-004
title: Producteurs externes → insight (point d'entrée unique du brut)
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-003, ADR-005, ADR-006]
tags: [architecture, producers, ingestion]
---

## Contexte

Plusieurs sources alimenteront cortex à terme : Claude Code JSONL, git/gh, NATS Lyra, mails (IMAP), Telegram (bot Lyra ou direct), voice (transcripts), à venir d'autres. Question : où publient-elles leur donnée brute ?

Deux options :

| Option | Description |
|---|---|
| Producteurs → memory directement | chaque source publie des entités/relations directement au graphe |
| Producteurs → insight, puis insight → memory | tout le brut transite par insight, qui extrait des observations et les publie à memory |

## Décision

**Tous les producteurs externes publient à cortex-insight, jamais à cortex-memory directement.**

Insight est le point d'entrée unique du brut dans l'écosystème.

## Conséquences

| Aspect | Impact |
|---|---|
| Insight | reçoit le brut de toute source · stocke en raw event log multi-source · pipelines de traitement par domaine |
| Memory | ne reçoit que des observations typées (cf. ADR-005) · ignore les détails de chaque source |
| Producteurs | ne dépendent que des contrats `roxabi-contracts.insight` (cf. ADR-006) · pas d'accès direct au graphe |
| Évolutivité | nouvelle source = nouveau producteur + nouveau pipeline dans insight · memory inchangé |
| Dedup raw | possible globalement dans insight (cross-source corrélation : un même événement peut arriver via 2 lanes) |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| Producteurs → memory direct | force memory à connaître chaque source · contamine le schéma graphe · perd la possibilité de dedup raw cross-source |
| Producteurs → un router séparé | sur-découpe sans bénéfice concret pour solo dev |
| Producteurs autonomes (chacun avec son store) | éclate le brut · pas de SSoT du « ce qui est arrivé » |

## Notes

Le mode d'arrivée du brut côté insight (push NATS / pull / hook filesystem) est laissé ouvert pour décision par source — voir ADR-007.

Pour les sources internes Roxabi (Lyra, voiceCLI), le bridge naturel est NATS : un service (`lyra-nats-bridge`) subscribe aux subjects `lyra.*` et republie sur `roxabi.insight.events.publish.{source}`. Pour les sources externes (mail IMAP, Telegram), un producteur dédié (`mail-ingest`, `telegram-ingest`) poll/subscribe et publie.
