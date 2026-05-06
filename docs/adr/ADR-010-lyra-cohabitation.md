---
adr: ADR-010
title: Cohabitation Lyra ↔ cortex (publisher seul ou aussi consumer ?)
status: deferred
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-004, ADR-005, ADR-009]
tags: [lyra, integration, scoping, deferred]
---

## Contexte

Lyra (`lyra-hub`, `lyra-telegram`, `lyra-discord`) est l'agent conversationnel multi-canal de Mickael. Il interagit avec :

- Mickael lui-même
- Potentiellement d'autres utilisateurs (si Lyra est exposé via Telegram/Discord à des tiers — Anya, amis, etc.)

Question : **comment Lyra cohabite avec cortex** ?

| Mode | Description |
|---|---|
| 1. Producer seul | Lyra publie ses événements (conversations, jobs, llm calls) à cortex-insight via NATS. Ne consomme pas. Garde sa propre mémoire interne. |
| 2. Producer + Consumer | Lyra publie ET querie cortex-memory pour son recall (au lieu d'avoir sa propre mémoire). Cortex devient la SSoT mémoire pour Lyra aussi. |
| 3. Hybride | Lyra publie · consomme certains namespaces (`world:*`, `self:mickael:*`) · maintient sa mémoire conversationnelle court-terme localement |

## Statut : deferred

Décision déférée parce qu'elle dépend de :

- **ADR-009** (taxonomie + namespacing) — sans namespacing, on ne peut pas scoper « ce que Lyra peut voir »
- L'existence du contrat NATS `lyra.memory.*` côté Lyra (Q18 du SP existant — ADR à écrire dans le repo Lyra)
- La question de la **vie privée croisée** : si Lyra parle avec Anya, est-ce que les souvenirs de cette conversation alimentent la mémoire personnelle de Mickael ? Sont-ils scopés à un namespace `lyra:user:anya` ?

## Pistes

### Pour le mode 1 (producer seul) — voie low-risk

- Lyra continue avec sa mémoire actuelle
- Publie observations à cortex (conversations, llm calls, jobs)
- Cortex extrait des entités utiles à Mickael (`world:person:anya`, `world:topic:X`, …)
- Lyra ne change pas son comportement immédiat

### Pour le mode 2 (producer + consumer) — voie ambitieuse

- Lyra remplace sa mémoire interne par des appels `roxabi.memory.query.*`
- Avant chaque réponse, Lyra fait `assemble(goal=user_query, scope=namespaces_visibles)`
- Cortex-memory devient la SSoT cognitive partagée

Implications :

- Lyra dépend de cortex-memory en hot-path (latence critique)
- Scoping nécessite namespaces robustes (un user Telegram tiers ne doit pas voir `self:mickael:*`)
- Ouvre la voie à la « mémoire partagée » entre les agents (Claude Code et Lyra peuvent référencer les mêmes entités)

### Pour le mode 3 (hybride)

- Lyra garde un cache court-terme local (mémoire conversationnelle session)
- Sur certains triggers (références à des personnes connues, concepts, projets), querie cortex-memory
- Compromis entre latence et richesse

## Bloquants pour décision finale

| # | Bloquant |
|---|---|
| 1 | ADR-009 (taxonomie) doit être réglée — sans namespaces, pas de scoping |
| 2 | ADR à écrire dans repo Lyra : contrat `lyra.memory.*` (Q18 du SP) |
| 3 | Décision produit Mickael : Lyra reste « pour moi » seul ou sera ouvert à des tiers ? |
| 4 | Si tiers : modèle de privacy par namespace (Anya ne voit pas la mémoire de Mickael) |

## Re-evaluation

À traiter après :
- Phase 1 cortex fonctionne (insight + memory live, observations Claude Code dans le graphe)
- ADR-009 décidée
- Question produit « scope Lyra » tranchée par Mickael
