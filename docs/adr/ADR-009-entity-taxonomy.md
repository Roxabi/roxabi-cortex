---
adr: ADR-009
title: Taxonomie des entités du graphe (biomimétisme psy/philo)
status: deferred
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-005, ADR-010]
tags: [taxonomy, ontology, biomimetic, deferred]
---

## Contexte

Le graphe de cortex-memory contient des entités (Personnes, Projets, RCs, Patterns, Skills, Concepts, Décisions…) reliées par des relations typées. La structure de cette taxonomie conditionne :

- Quels types d'observations on doit produire côté insight (ADR-005)
- Comment scoper la mémoire (perso vs partagée Lyra — ADR-010)
- Quels handlers du Retain Job doivent exister
- Quelles requêtes l'API memory doit savoir servir

Une intuition initiale a été posée : **monde extérieur** (Personnes, Organisations, Projets, Contrats…) vs **monde intérieur** (RCs, Patterns, Préférences, Persona des agents). Cette dichotomie est plausible mais doit être challengée.

## Statut : deferred

L'utilisateur a explicitement demandé d'approfondir via biomimétisme — psychologie cognitive, phénoménologie, théorie de l'esprit, théories de la communication. Pas de décision figée pour l'instant.

## Pistes à explorer

### Cadres pertinents

| Cadre | Apport potentiel |
|---|---|
| **Tulving** (taxonomie des mémoires) | Distinction épisodique / sémantique / procédurale — empiriquement solide, fondatrice |
| **Phénoménologie** (Husserl, Merleau-Ponty) | noème (objet visé) vs noèse (acte) · Lebenswelt (monde-vécu) · objets ¬ indépendants mais objets-pour-moi/pour-l'agent |
| **Théorie de l'esprit (ToM)** | Modéliser les états mentaux d'autrui — clé pour modéliser les agents et leur perception croisée |
| **Speech Act Theory** (Austin, Searle) | Communiquer = agir — typer les interactions par acte (assertif, directif, commissif, expressif, déclaratif) |
| **Modèles internes opérants** (Bowlby) | Représentations mentales des relations — utile pour `agent:*:relationship:*` |
| **Bio-inspiration hippo-memory** (déjà adoptée) | Hippocampe = épisodique court-terme · cortex = sémantique long-terme · pattern de consolidation nuit |

### Direction émergente — grille 2D (proposée, ¬ décidée)

**Axe 1 — type de mémoire (Tulving)**
- épisodique : ce qui s'est passé · événements horodatés
- sémantique : ce qui est vrai sur le monde · faits, descriptions
- procédurale : comment on fait · skills, routines

**Axe 2 — référent**
- self : moi (Mickael)
- agent : Lyra, Claude Code, futurs
- other : personnes, organisations
- object : projets, artefacts, lieux
- abstract : concepts, valeurs, principes

L'intuition ext/int devient une lentille sur l'axe 2 (self+agent = intérieur · other+object = extérieur · abstract = transversal).

### Stratégies de communication (à intégrer)

Speech act theory pour typer les interactions :

| Acte | Exemple |
|---|---|
| Assertif | "tel projet est en pause" |
| Directif | "fais X" |
| Commissif | "je livre vendredi" |
| Expressif | "j'en ai marre de ce bug" |
| Déclaratif | "tu es promu" |
| Interrogatif | "où en est le PR ?" |

Permet des analyses fines : « Mickael est principalement directif avec Claude Code, expressif avec Anya » → patterns dans `self:mickael:comm-pattern:*`.

## Bloquants pour décision finale

- Interview structurée nécessaire (skill `dev-core:interview` mode brainstorm)
- Note de cadrage taxonomique à produire dans `artifacts/analyses/` avant de figer le DATA-MODEL memory
- Validation contre cas concrets (mails Anya, sessions /dev, calls clients) avant de figer

## Conséquences (anticipées)

| Aspect | Impact attendu |
|---|---|
| Schéma `entities` | colonnes `type` et `subtype` deviennent path-style namespacés (ex. `world:person:anya`) plutôt qu'enum plat |
| Retain Job | handlers indexés par `(category_observation, target_namespace)` |
| Compiled Truth | au moins 2 templates : « ext » (description + history) vs « int » (capabilities + patterns + instructions actives) · + 1 template `interaction-thread` pour résumer N interactions |
| Decay σ | varie par niveau de la cartographie · `world:*` long · `agent:*:rc:*` court · `agent:*:instruction:*` long ou pinned |

## Re-evaluation

À traiter avant l'implémentation du schéma graphe memory. Bloque l'écriture de `docs/memory/DATA-MODEL.md` final.

Étape : interview biomimétique → note de cadrage `artifacts/analyses/taxonomy-cortex-YYYY-MM-DD.md` → cet ADR-009 passe en `accepted` ou est superseded par un ADR concret.
