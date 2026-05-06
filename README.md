# roxabi-cortex

Exocortex personnel — capture multi-source, mémoire structurée vivante, sert les agents.

> Repo encore nommé `roxabi-insight` ; renommage en `roxabi-cortex` à venir (cf. ADR-001).
> **Status :** design phase finalisée 2026-05-06 · implémentation pas commencée.

---

## Why

Tout ce qui passe sous les mains de l'utilisateur — sessions Claude Code, conversations Telegram, mails, git, voice, NATS Lyra — laisse une trace. cortex la capte, l'agrège en mémoire structurée (graphe d'entités avec decay), devient la source unique de vérité cognitive, alimente les agents en retour, et se referme sur lui-même via l'actuation (PRs sur CLAUDE.md / skills / memory).

L'asset long-terme = le graphe. Le reste (parsers, pipelines, détecteurs, classifiers, reports) est remplaçable.

---

## Architecture

cortex se compose de **2 services** + producteurs externes + consommateurs.

```
                  Consommateurs
        Claude Code · Lyra · reports
                  ▲
                  │ query
                  │
          ┌────────────────┐
          │ cortex-memory  │  warehouse + consolidation + assemble + actuate
          └───────▲────────┘
                  │ Observation (typée)
          ┌───────┴────────┐
          │ cortex-insight │  lake + encodage (raw + ETL)
          └───────▲────────┘
                  │ RawEventEnvelope
                  │
                  Producteurs
        Claude Code JSONL · git/gh · NATS Lyra · mail · telegram · …
```

| Service | Rôle | Évolue |
|---|---|---|
| **cortex-insight** | accueille tout le brut · stocke en raw event log · pipelines ETL par domaine · produit des observations typées | rapide |
| **cortex-memory** | reçoit les observations · consolide en graphe · decay · compiled truth · assemble · actuate · sert les consommateurs | lente (asset long-terme) |

Voir `docs/ARCHITECTURE.md` pour la vue détaillée et `docs/adr/` pour les décisions.

---

## Statut

**Design phase finalisée** (2026-05-06) :

- 11 ADRs publiés · architecture lake/warehouse · contrat `Observation` · containerisation Podman+Quadlet · monorepo workspace · DuckDB v1
- 3 décisions encore ouvertes/déférées : ADR-007 (mode arrivée par source) · ADR-009 (taxonomie entités) · ADR-010 (cohabitation Lyra)

**Implémentation pas commencée.** Bloquants avant code :

- ADR-009 (taxonomie) — interview biomimétique nécessaire
- Renommage repo `roxabi-insight` → `roxabi-cortex`
- Scinder le SP actuel en `spec-cortex-insight.md` + `spec-cortex-memory.md`
- Étendre `roxabi-contracts` côté Lyra (sous-modules `insight.py` + `memory.py`)

---

## Quick Start

```
# Pas implémenté — voir docs/ARCHITECTURE.md et docs/adr/
```

Une fois implémenté :

```bash
make cortex-insight start
make cortex-memory start

# côté insight : ingest + détecteurs
cortex-insight ingest --since 7d --projects lyra
cortex-insight detect

# côté memory : query
cortex-memory entity slug "rc:RC-2"
cortex-memory assemble --goal "issue:1234" --budget 4000
```

---

## Tech Stack

| Composant | Choix |
|---|---|
| Python | 3.13 |
| Package manager | uv + hatchling (uv workspace) |
| CLI | typer |
| Storage | DuckDB v1 (ADR-011 · cible conditionnelle KuzuDB pour memory) |
| Parsing | polars |
| Sanitization | trufflehog + regex + entropy |
| Incremental ingest | cocoindex (Lane 1 JSONL) |
| Bus | NATS via roxabi-contracts |
| LLM (Phase 2) | LiteLLM → fireworks.ai → Kimi K2.5/K2.6 ou GLM 5 |
| Containerisation | Podman + Quadlet (ADR-002) |
| Tests | pytest |
| Lint/format | ruff · pyright |

LLM non-Anthropic par design : élimine le biais same-model lors de l'évaluation des transcripts Claude Code.

---

## Phasing

| Phase | Ajoute | Coût LLM |
|---|---|---|
| 1 | insight (Lane 1+2 ingest, D1-D15, outcome, observations) · memory (graphe basique, Retain Job, compiled truth) · contracts | $0 |
| 1.5 | NATS Lane 3 (Lyra) · buffer · richer strength formula · adaptive decay | $0 |
| 2 | LLM analyst · DAG-aware assemble · goal stack · dark matter mining | ~$10-30/run |
| 3 | Layer 4 actuation (approval queue + auto-PR) · conflict detection · GEPA · correction latency | ~$1-5/run |
| 4 | GEPA on CLAUDE.md sections · `lyra.memory.*` subjects live · multi-host corpus merge | TBD |

---

## Non-Goals

- Real-time enforcement / "Adversarial Orchestrator"
- "Thinking Ratio" KPI ou métriques Goodhart-trivial
- Behavior prescription (cortex surface patterns · remediation via approval queue)
- Multi-agent orchestrator (→ `roxabi-live`)
- roxabi-vault et 2ndBrain (deprecated)

---

## Documentation

| Document | Rôle |
|---|---|
| `docs/ARCHITECTURE.md` | vue d'ensemble actuelle |
| `docs/adr/README.md` | index decision log |
| `docs/adr/ADR-NNN-*.md` | une décision par fichier · frontmatter + sections fixes |
| `docs/DATA-MODEL.md` | **schéma historique** · superseded partiellement · à scinder |
| `artifacts/specs/spec-roxabi-insight.md` | **SP historique** · superseded partiellement · à scinder |

---

## License

TBD
