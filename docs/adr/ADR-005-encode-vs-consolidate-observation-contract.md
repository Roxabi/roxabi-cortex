---
adr: ADR-005
title: Encode (insight) vs consolide (memory) — contrat `Observation`
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-003, ADR-004, ADR-006]
tags: [architecture, contract, biomimetic, frontier]
---

## Contexte

ADR-003 pose la frontière lake/warehouse, ADR-004 pose que tout le brut entre par insight. Mais : **où vit la "génération des souvenirs"** ? Le passage du raw au structuré n'est pas atomique — il a deux composantes :

1. **Découverte** dans la donnée brute (parser, typer, extraire le sens) — nécessite la connaissance de la source
2. **Intégration** dans le graphe existant (dedup, conflict, schema_fit, decay) — nécessite la connaissance de l'état du graphe

Si on met tout côté insight, memory devient idiot et insight doit connaître l'état du graphe. Si on met tout côté memory, memory doit connaître chaque source. Aucun découpage propre.

## Décision

**La génération des souvenirs traverse les deux services en deux temps.** Inspiré du modèle biologique cerveau (hippocampe encode → cortex consolide) :

| Étape | Service | Connaissance requise |
|---|---|---|
| **Encodage** | cortex-insight | source-spécifique (sémantique du domaine — ce qu'est un mail, un tool call, un message Telegram) |
| **Consolidation** | cortex-memory | graphe-spécifique (état actuel des entités, dedup, schema_fit, conflicts, decay) |

Le **contrat publish entre les deux** est `Observation` — un fait typé, encodé, **pas encore résolu contre le graphe**.

```python
class Observation(BaseModel):
    """An encoded fact from a source — not yet resolved against the graph."""
    id: ULID
    source: str                      # "claude-code-jsonl" | "mail" | "telegram" | …
    source_ref: str                  # natural ID in source
    timestamp: int                   # epoch ms
    category: ObservationCategory    # interaction | finding | decision | artifact | …
    actors: list[ActorRef]           # references to identifiable entities (email, name, slug if known)
    topic: list[str] | None          # extracted topics/concepts
    sentiment: str | None
    payload_typed: dict              # category-specific structured payload
    correlation: dict                # trace_id, parent_obs_id, episode_id, …
```

Memory subscribe au sujet `roxabi.memory.observations.publish` · pour chaque `Observation` reçue, le **Retain Job** (vit dans memory) :

1. résout les `actors` → entités existantes ou nouvelles
2. dedup contre le graphe
3. compute `schema_fit`
4. détecte conflits
5. écrit entités + relations
6. met à jour `memory_strength`, decay
7. déclenche regen de `compiled_truth` si impact > seuil

## Conséquences

| Aspect | Impact |
|---|---|
| Insight | sait parser ses sources · ignore l'état du graphe · publie des `Observation` typées par catégorie |
| Memory | ignore comment parser un mail ou un JSONL · sait consolider toute `Observation` quelle que soit son origine |
| Contrat | `Observation` (et non `EntityProposal` direct) — découplage propre |
| Catégories d'observation | doivent être stables et exhaustives (Interaction, Finding, Decision, Artifact, Statement…) — leur taxonomie est partie intégrante de ADR-009 |
| Retain Job | déménage de insight (formalisation initiale) à memory (révision) · la consolidation devient attribut du warehouse |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| Toute la génération dans insight (`EntityProposal` final) | force insight à connaître l'état du graphe · couple les pipelines au schéma graphe · empêche memory d'arbitrer dedup |
| Toute la génération dans memory (insight = lake passif pur) | memory devient lourd · doit contenir parsers de chaque source · contamine le schéma générique du warehouse |
| Pipeline unique cross-service via NATS streaming | complexité prématurée · les deux temps sont logiques distincts, mieux vaut les nommer |

## Notes

L'analogie biomimétique :

| Cerveau | Cortex (notre système) |
|---|---|
| Perception (sens) | producteurs externes |
| Encodage (hippocampe) — souvenir épisodique typé | cortex-insight |
| Consolidation (cortex sémantique) — intégration durable | cortex-memory |
| Récupération (cortex préfrontal + goal-conditioned) | memory.assemble + goal stack |

Cohérent avec le modèle hippo-memory déjà adopté pour la formule de strength. Voir aussi ADR-001 pour le naming.

La taxonomie des catégories d'observation et des entités produites est traitée dans ADR-009 (DEFERRED — interview biomimétique nécessaire).
