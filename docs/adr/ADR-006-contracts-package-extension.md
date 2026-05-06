---
adr: ADR-006
title: Extension de roxabi-contracts (sous-modules insight + memory)
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-004, ADR-005]
tags: [contracts, nats, protocol, interop]
---

## Contexte

Le package `roxabi-contracts` existe dans le monorepo Lyra (`lyra/packages/roxabi-contracts/`). Il définit :

- Schemas Pydantic des messages NATS (Job, JobResult, JobProgress, LlmRequest, VoiceTtsRequest, ImageGenRequest…)
- Subject literals (constantes string : `lyra.jobs.submit`, etc.)
- `ContractEnvelope` (wrapper standard avec `trace_id`, `created_at`, version)
- Trust model implicite (qui peut publier/consommer quoi)

Pattern : **les contracts sont la SSoT du protocole · les implémentations sont remplaçables**. Tout module Roxabi qui veut se plug doit dépendre des contracts, pas des implémentations. Cela permet à n'importe quel nouveau module de se brancher.

Question : comment cortex (insight + memory) s'inscrit dans ce système ?

## Décision

**Étendre `roxabi-contracts` avec deux sous-modules** : `insight.py` et `memory.py`. Ne pas créer de package séparé.

```
lyra/packages/roxabi-contracts/
├── envelope.py              # ContractEnvelope (existant)
├── jobs.py                  # JobRequest, JobResult, JobProgress (existant)
├── llm.py                   # LlmRequest, LlmResponse (existant)
├── voice.py                 # VoiceTtsRequest, VoiceSttRequest (existant)
├── image.py                 # ImageGenRequest (existant)
├── conversation.py          # ConversationTurnEvent (à créer — Q17 ouvert)
├── insight.py               # NEW — raw event publish vers insight
└── memory.py                # NEW — observation publish + query memory
```

### `insight.py` — schémas pour publier du brut vers insight

```python
class RawEventEnvelope:
    """Wrapper standard pour publier un event brut à cortex-insight."""
    id: ULID
    source: str                  # "claude-code-jsonl" | "lyra-nats" | "mail" | "telegram" | …
    source_ref: str              # ID natif (file+offset, msg-id, NATS subject+seq, sha)
    timestamp: int
    payload: dict                # JSON brut sanitized (schema spécifique au source)
    correlation: dict            # trace_id, parent_id, …

# Subjects:
#   roxabi.insight.events.publish.{source}     — publish raw events
#   roxabi.insight.fetch.{source}              — admin fetch (debug)
```

### `memory.py` — schémas pour publier des observations + querier memory

```python
# Publish (insight → memory)
class Observation(BaseModel):
    """Encoded fact from a source — see ADR-005."""
    # cf. ADR-005 pour le schéma complet

# Query (consumers → memory)
class EntityQueryRequest(BaseModel): ...
class EntityQueryResponse(BaseModel): ...
class AssembleRequest(BaseModel):
    goal: str | None
    budget_tokens: int = 4000
    fresh_tail_days: int = 7
class AssembleResponse(BaseModel): ...

# Subjects:
#   roxabi.memory.observations.publish         — insight publishes
#   roxabi.memory.query.entities               — consumers ask
#   roxabi.memory.query.assemble               — Claude Code /dev, Lyra recall
#   roxabi.memory.query.compiled               — get compiled truth
#   roxabi.memory.actuate.approve              — approval queue ops
```

## Conséquences

| Aspect | Impact |
|---|---|
| Producteurs externes | ne dépendent que de `roxabi_contracts.insight` · zéro coupling à insight implémentation |
| Consommateurs | ne dépendent que de `roxabi_contracts.memory` · zéro coupling à memory implémentation |
| Versionnage | les contracts sont la SSoT versionnée · changements rétro-incompatibles → bump major |
| Localisation | reste dans `lyra/packages/roxabi-contracts/` (cohérence avec le monorepo Lyra existant) |
| Distribution | uv GitHub source (pattern existant) : `roxabi-contracts = { git = "...lyra.git", subdirectory = "packages/roxabi-contracts" }` |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| Package séparé `roxabi-memory-contracts` | sur-fragmenté pour solo dev · perd la cohérence "un seul protocole Roxabi" · friction |
| Définir les contracts dans cortex-memory directement | force tout consommateur à dépendre de memory · perd l'idée même de contrat |
| HTTP/REST au lieu de NATS | ¬cohérent avec le bus existant · perd les bénéfices pub/sub (multi-consumer, replay, durabilité) |

## Notes

Le pattern « contracts = SSoT du protocole » vient de Lyra et est cadré par ADR-049 (lyra). On hérite de cette discipline.

Si à l'avenir cortex devient un projet vraiment indépendant de Lyra, on pourra extraire les contracts dans leur propre repo. Pour l'instant, la cohabitation dans le monorepo lyra est plus simple.
