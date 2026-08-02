# Spec v1 — cortex memory MCP (Cloudflare)

status: draft v1 · 2026-07-19 · arbitrages A1-A8 clos avec Mickael
inspiration (¬vérité) : `docs/archive/memory-system-v0-2026-04/`, `artifacts/specs/spec-cortex-memory.md` (ère DuckDB), `gosilex/silex-hub/00_COCKPIT/silex-hub-memory-design.md`
inputs mesurés : `../analyses/memory-design-inputs-2026-07.claude.md` (compat outils + sizing corpus)

## Objectif

Memory system pour agents (Claude Code, Grok, Codex futur) remplaçant les pointeurs épars AGENTS.md/CLAUDE.md. Design silex (3 plans) + MCP remote sur Cloudflare.

## Principes

- P1 — fichiers = SSoT · index = dérivé rebuildable · contexte assemblé = éphémère
- P2 — 1 info = 1 home ; tier lisible depuis le path
- P3 — naissance en hot (T3) ; promotion = acte explicite
- P4 — promotion/consolidation = gate humain, jamais auto-apply
- P5 — budget T0 dur ~2-3k tokens
- P6 — decay, pas delete (chaîne raw→distilled→superseded→archived)
- P7 — savoir ≠ faire : skills/plugins hors memory
- P8 — buffers propriétaires (memory Claude native) = capture, drainés vers le store
- P9 — provenance obligatoire (verified/inferred/assumed)
- P10 — 1 source → N projections générées (canon → CLAUDE.md/AGENTS.md par outil)

## Tiers × garantie de présence

| Tier | Contenu | Garantie | Où |
|---|---|---|---|
| T0 Canon | invariants, oubli=incident | injecté (harness) | fichiers locaux (projections) |
| T1 Froid | savoir durable | recall MCP / pointeur | store `global/` + `{repo}/docs/**` |
| T2 Épisodique | leçons, feedback, goals | recall MCP (`context_build`) | store `episodic/` |
| T3 Chaud | périssable | recall si récent | store `hot/` + `{repo}/artifacts/**` |

Scopes orthogonaux : global (opérateur) / fleet (~/projects) / repo.

## Carte des datas

```
┌─ MACHINES — plan INJECTION (harness, jamais MCP) ────────────────────┐
│ ~/.claude/CLAUDE.md       T0 global      ← PROJECTION générée         │
│ ~/.grok/AGENTS.md         T0 delta grok  ← projection générée         │
│ ~/.codex/AGENTS.md        T0 (futur)     ← projection générée         │
│ ~/projects/ssot/*.ssot.md T0 fleet       SSoT en place (projects-meta)│
│ {repo}/AGENTS.md (+CLAUDE.md=@AGENTS.md) T0 repo   SSoT en place      │
│ {repo}/docs/**            T1 repo        SSoT en place, on-demand     │
│ {repo}/artifacts/**       T3 repo        SSoT en place, périssable    │
└──────────────────────────────────────────────────────────────────────┘
        ▲ génération (canon/)                    │ write = commit (MCP)
┌─ STORE — SSoT memory (1 domaine = 1 repo git privé) ─────────────────┐
│ cortex-store (perso) :                                                │
│   canon/     sources T0 → projetées vers fichiers locaux              │
│   global/    T1 docs setup/habitudes cross-repo                       │
│   episodic/  T2 leçons · feedback · goals                             │
│   hot/       T3 notes expirables cross-repo                           │
│ MD + frontmatter (type, scope, status, provenance) + [[wikilinks]]    │
│ + domaines partagés futurs (ex. silex) = autres repos                 │
└──────────────────────────────────────────────────────────────────────┘
        │ sync git → R2 (webhook/CI)
┌─ CLOUDFLARE — dérivé pur, rebuildable ───────────────────────────────┐
│ R2          miroir du store = source d'ingest AI Search               │
│ AI Search   managé : chunk → embed → Vectorize, sync continu,         │
│             hybrid retrieval + rerank + metadata filter               │
│ Vectorize   index vecteurs (provisionné par AI Search)                │
│ D1          index structurel : frontmatter, backlinks, domaines/ACL   │
│             (+ queue approbation V2)                                  │
│ Worker MCP  OAuth · search / get / write / context_build              │
└──────────────────────────────────────────────────────────────────────┘
```

## Flows

- write : agent → `write` → commit GitHub API (repo domaine) → sync R2 → réindex AI Search + D1
- read : agent → `context_build(goal, budget)` → AI Search (sémantique hybride) + D1 (méta/backlinks) → pack sous budget
- inject : harness lit les fichiers T0 locaux — le MCP ne peut pas injecter ; T0 contient le protocole d'usage MCP (pont)
- project : `canon/` → générateur → `~/.claude/CLAUDE.md`, `~/.grok/AGENTS.md`, `~/.codex/AGENTS.md`
- consolidation : manuelle (A7) — promotions T3→T2→canon = commits via gate humain

## Surface MCP v1

| Tool | Rôle |
|---|---|
| `search(query, filters)` | recall hybride (AI Search) + filtres méta (D1) |
| `get(id)` | doc complet + backlinks |
| `write(doc, tier, domain)` | commit dans le repo domaine (naissance en `hot/` par défaut) |
| `context_build(goal, budget)` | pack assemblé : T2 pertinent + goals actifs + pointeurs T1 + fresh tail |

Auth : OAuth multiuser (standard MCP). Domaines : Perso = user-only · partagé = owner/member/reader, owners décident des droits. ACL appliquée au niveau Worker (D1 mapping), jamais par accès git direct des lecteurs.

## Arbitrages actés

| # | Décision |
|---|---|
| A1 | tout fichiers — 1 domaine = 1 repo git ; CF = dérivé ; write = commit via MCP |
| A2 | authz par domaine : Perso / owner-member-reader ; droits fins ultérieurs |
| A3 | home = roxabi-cortex ; base boilerplate silex ; bench TS/Python/Rust à faire (biais TS : McpAgent, workers-oauth-provider, SDK MCP officiels) |
| A4 | Vectorize direct via **AI Search** (ex-AutoRAG) managé — hybride natif, ¬FTS custom |
| A5 | OAuth multiuser (roles par domaine dans les claims) |
| A6 | 4 tools v1 ; relations = [[wikilinks]] lus par l'index ; graph/entités V2 |
| A7 | tout manuel v1 ; cron/triggers plus tard |
| A8 | canon global = `~/.claude/CLAUDE.md` flat ; `~/.grok/AGENTS.md` = delta grok minimal |

## V2 (défère explicitement)

- graph entités/relations en écriture (ADR-009 = blocage intellectuel assumé) — émergence GraphRAG depuis la table de liens d'abord
- dream loop (logs → candidats scorés → queue → gate → promote) + cron triggers
- ingest des `{repo}/docs/**` dans AI Search (v1 : store seul)
- decay scoré / memory_strength dans `context_build`
- droits domaine fins ; instance AI Search par domaine vs metadata filter (v1 : 1 instance + filtre)

## Ouvert

- bench langage Worker (TS vs Python vs Rust) — A3
- nom + emplacement GitHub du repo `cortex-store`
- mécanisme sync git→R2 (GitHub Action push-mirror vs webhook Worker)
