# Archive — memory-system v0 (avril 2026, ex roxabi-factory)

> **Statut : SUPERSÉDÉ.** Spec mémoire originale (« SP original »), rédigée avril 2026 dans
> `roxabi-factory/docs/memory-system/`, déplacée ici 2026-06-10 (factory ADR-087 :
> cortex = SSoT mémoire long-terme). Les concepts ont été repris et re-décidés par les
> ADRs/specs cortex ci-dessous — **ne pas implémenter depuis ces fichiers**.

## Pourquoi archivé ici

Trois designs mémoire coexistaient sans arbitrage (critical review factory 2026-06-09 §6) :
L0-L4 factory (code partiel), cette spec (PostgreSQL/pgvector, « ready for implementation »),
et roxabi-cortex (DuckDB, NATS-only). Le harness factory (#1490) a tranché : injection mémoire
via cortex. Cette spec est le **prédécesseur direct** de cortex — mêmes concepts, mêmes termes
(Compiled Truth, Retain Job, decay Ebbinghaus, consolidation nocturne) — mais ses choix
techniques sont contredits par les ADRs cortex plus récents.

## Carte de supersession

| Fichier v0 | Supersédé par (cortex) | Delta clé |
|---|---|---|
| `00-summary.md` | `docs/ARCHITECTURE.md` + `artifacts/specs/spec-cortex-memory.md` | 4 couches → split lake/warehouse 2 services (ADR-003) |
| `01-raw-layer.md` | ADR-003 + `spec-cortex-insight.md` | Raw immuable → lake cortex-insight (event log lane-tagged) |
| `02-knowledge-graph.md` | ADR-011 + ADR-009 (deferred) + `spec-cortex-memory.md` | **PostgreSQL/pgvector → DuckDB v1** (triggers KuzuDB) ; taxonomie entités = ADR-009 |
| `03-compiled-truth.md` | `spec-cortex-memory.md` (compiled truth) | concept repris tel quel |
| `04-consolidation-nightly.md` | ADR-005 + Retain Job (`spec-cortex-memory.md`) | nightly monolithique → encode (insight) vs consolidate (memory) |
| `05-agent-usage.md` | ADR-010 (cohabitation Lyra) + factory `1490-harness-design-spec.mdx` | accès direct → request-reply NATS `roxabi.memory.query.assemble` |
| `06-execution-model.md` | `docs/ARCHITECTURE.md` (topologie NATS) | sync/async in-process → subjects NATS (ADR-006 contracts) |
| `07-decay-mechanism.md` | `spec-cortex-memory.md` (hippo-decay) | Ebbinghaus repris, paramétrage à re-deriver |
| `08-implementation-prompts.md` | — **non repris** | prompts à re-deriver après ADR-009 (taxonomie) |
| `REFERENCES*.md` | — | archivés tels quels |
