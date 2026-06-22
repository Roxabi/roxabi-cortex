@.claude/stack.yml

# CLAUDE.md — Instructions for Claude Code (roxabi-cortex)

Let:
  P  := CLAUDE.md path
  EC := `~/projects/CLAUDE.md` (ecosystem : release convention, supervisor pattern, cross-project deps)
  AR := `docs/ARCHITECTURE.md` (vue d'ensemble · réfère aux ADRs)
  DL := `docs/adr/` (decision log · SSoT des décisions architecturales)

## Project

**roxabi-cortex** — exocortex personnel · 2 services (cortex-insight = lake + ETL ; cortex-memory = warehouse + graphe vivant) · ingestion multi-source · contracts NATS via roxabi-contracts.

→ AR pour la vue d'ensemble · DL pour les décisions · ADR-001..011.

## TL;DR

- Repo = `Roxabi/roxabi-cortex` (public) · path local = `~/projects/roxabi-cortex/`
- Découpage logique : insight (raw + encodage) / memory (graphe + consolidation + assemble + actuate) — ADR-003
- Contrat publish entre les deux : `Observation` typée — ADR-005
- Producteurs externes (Claude Code, mail, telegram, NATS Lyra) → insight uniquement — ADR-004
- Containerisé Podman + Quadlet · cohérent écosystème Lyra — ADR-002
- 1 repo monorepo workspace · `packages/{insight,memory}` — ADR-008
- Storage : DuckDB v1 · revisit memory→KuzuDB si triggers — ADR-011

## Status

**Design phase — architecture finalisée 2026-05-06.** Implémentation pas commencée.

Bloquants avant implémentation :
- ADR-009 (taxonomie entités) à régler via interview biomimétique
- Contracts à étendre côté `lyra/packages/roxabi-contracts/` (issue #3, blocked-by #2)

## Stack

| Composant | Choix |
|---|---|
| Python | 3.13 |
| Package manager | uv + hatchling · uv workspace pour monorepo |
| CLI | typer |
| Storage | DuckDB v1 partout (ADR-011) · KuzuDB cible conditionnelle pour memory |
| Parsing | polars |
| Sanitization | trufflehog (`--no-verification`) + regex + path normalizer |
| Incremental ingest | cocoindex (Lane 1 JSONL) |
| LLM (Phase 2) | LiteLLM → fireworks.ai → Kimi K2.5/K2.6 ou GLM 5 |
| nats-py | ≥ 2.7 |
| roxabi-contracts | uv GitHub source · sous-modules `insight.py` + `memory.py` (ADR-006) |
| Tests | pytest |
| Lint/format | ruff |
| Typecheck | pyright |

## Key files

| Fichier | Rôle |
|---|---|
| `docs/ARCHITECTURE.md` | vue d'ensemble (à jour) |
| `docs/adr/README.md` | decision log (index) |
| `docs/adr/ADR-NNN-*.md` | 1 fichier par décision · frontmatter YAML · sections fixes |
| `artifacts/specs/spec-roxabi-insight.md` | **SP historique · superseded partiellement par les ADRs · à scinder** |
| `docs/DATA-MODEL.md` | **schéma historique · superseded partiellement par les ADRs · à scinder** |
| `pyproject.toml` (root) | uv workspace racine (à créer) |
| `packages/insight/` | service lake + ETL (à créer) |
| `packages/memory/` | service warehouse + serve (à créer) |
| `Makefile` (root) | cibles `cortex-insight {start,stop,reload,logs}` + idem memory |

## Pipeline

```
Producteurs externes (Claude Code, git/gh, NATS Lyra, mail, telegram, …)
       │ RawEventEnvelope
       ▼
cortex-insight  ── raw events → pipelines (behavioral, relationship, …) → Observations
       │ Observation
       ▼
cortex-memory   ── Retain Job → entités + relations → decay → compiled truth → assemble → actuate
       │ assemble / query
       ▼
Consommateurs (Claude Code /dev, Lyra recall, reports)
```

## Key concepts

| Terme | Définition |
|---|---|
| Cortex | l'écosystème complet (ADR-001) |
| Insight | service lake + encodage |
| Memory | service warehouse + consolidation + serve |
| Observation | contrat publish insight→memory · fait typé encodé · pas encore résolu graphe (ADR-005) |
| Retain Job | consolidation des Observations en entités+relations · vit dans memory |
| Episode | unité tâche-bornée Claude Code (intent + start + end + branch + outcome) |
| Outcome | enum 8 états (SUCCESS_CLEAN..PENDING) |
| RC-1..RC-7 | 7 root causes Mickael (cf. SP) |
| Entité | nœud du graphe : namespace + slug + type + subtype + strength + decay + … |
| Compiled Truth | per-entity markdown · regen nightly via impact analysis |
| Actuation | approval queue + auto-PR vers CLAUDE.md/skills/memory |
| Decay | `weight_temporal = exp(-Δt/σ)` · old patterns auto-fade · recurring reinforce |
| Schema fit | 0..1 · fit à patterns existants · <0.3 dark matter · >0.7 fast-track |

## Conventions

- EN pour code/docs/commits techniques · FR pour échanges avec Mickael
- Commits Conventional (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
- Branches : numérotées si issue (`1-add-tier-a-detectors`) · descriptives sinon
- PRs : merge-commit only (¬squash) — per EC
- Release tags : `roxabi-cortex/vX.Y.Z` (post-renommage) — per EC
- Issues : `/dev #N`
- Décisions architecturales : ADR · jamais éditer un ADR `accepted` à la légère, en créer un nouveau qui supersedes

## Non-goals (locked)

- Real-time enforcement / "Adversarial Orchestrator" prompts
- "Thinking Ratio" KPI ou métriques Goodhart-trivial
- Behavior prescription (surface patterns · remediation via approval queue, ailleurs)
- Multi-agent orchestrator (→ `roxabi-live`)
- roxabi-vault et 2ndBrain (deprecated · pas migrés)

## Pour les agents

Avant toute action structurante :

1. Lire `docs/ARCHITECTURE.md` pour la vue d'ensemble
2. Lire les ADRs pertinents au sujet (ex. proposer un changement de storage → lire ADR-011)
3. Si la question n'a pas d'ADR → la décision n'a pas été prise · proposer DP(A) à Mickael avec options et ne pas trancher seul
4. Pour proposer une alternative à un choix existant, lire l'ADR et son raisonnement (alternatives écartées) avant de re-suggérer
5. Si on décide quelque chose nouveau pendant le travail → écrire un ADR avant d'implémenter

## CLAUDE.md hygiene

| P | Scope |
|---|---|
| `CLAUDE.md` (root) | racine projet |
| `packages/insight/CLAUDE.md` | à créer si insight package grandit (≥3 subdirs) |
| `packages/memory/CLAUDE.md` | idem |

Rules : add/delete/move → update P · new `packages/{insight,memory}/` subdir → P le plus proche · ¬nested CLAUDE.md inutile.
