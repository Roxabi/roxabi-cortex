# Inputs design memory MCP — compat outils + sizing corpus

status: snapshot 2026-07-18/19 · inputs de `../specs/spec-cortex-mcp-v1.md` · périme vite (versions outils, tailles)

## 1. Matrice compat chargement contexte (vérifiée 2026-07-18)

| Outil | Version | Comportement vérifié |
|---|---|---|
| Grok CLI | 0.2.103 | Claude-compat **ON par défaut** : charge `~/.grok/AGENTS.md` **ET** `~/.claude/CLAUDE.md` au niveau user ; accepte `AGENTS.md` / `CLAUDE.md` / `CLAUDE.local.md` / `AGENT.md` — **les deux chargés si les deux présents = risque double-injection** ; charge `.claude/rules/` et `.cursor/rules/` par niveau ; le plus profond gagne. Source : `~/.grok/docs/user-guide/12-project-rules.md` |
| Grok CLI | 0.2.77 (header `~/.grok/AGENTS.md`, stale) | `@file` **non expansé** (~73 tokens littéraux) — à re-vérifier sur 0.2.103 avant de compter sur l'expansion |
| Claude Code | courant | **¬AGENTS.md natif** ; pont = `CLAUDE.md` contenant `@AGENTS.md` (expansé au launch, **max 4 hops**, `@~/` OK) ou symlink ; `~/.claude/rules/*.md` auto-chargés, frontmatter `paths:` = chargement conditionnel |
| Codex | ¬installé | prospectif — lit `AGENTS.md` nativement |

Conséquences (→ A8 acté) :

- Canon global = `~/.claude/CLAUDE.md` flat (Claude natif + Grok compat le lisent tous deux)
- `~/.grok/AGENTS.md` réduit au **delta grok** (sinon double-injection user-level)
- Per-repo : `AGENTS.md` = source + `CLAUDE.md` = 1 ligne `@AGENTS.md` (Claude expanse ; Grok charge les deux = ~3 tokens de surcoût ; Codex lit AGENTS.md)
- État actuel : `~/.claude/CLAUDE.md` **n'existe pas** ; `~/.grok/AGENTS.md` = symlink → `~/.claude/dotfiles/grok/AGENTS.md` (repo git dotfiles)

## 2. Sizing corpus (mesuré 2026-07-18 · ≈ tokens = octets/3,7)

Périmètre Roxabi = repos propres, hors `external_repos/`, `archived/`, `gosilex/` :

| Corpus | Tier | Fichiers | Octets | ≈ tokens |
|---|---|---|---|---|
| `ssot/*.ssot.md` | T0 fleet | 6 | 13 168 | 3,5k |
| CLAUDE/AGENTS/GROK/README racine (maxdepth 2) | T0 repo | 72 | 481 155 | 130k |
| `*/docs/**` | T1 | 833 | 8 335 221 | 2,2M |
| `*/artifacts/**` | T3 | 214 | 2 839 050 | 750k |
| Memory Claude native (`~/.claude/projects/*/memory/`) | T2 | 40 | **99 406** | **26k** |
| `~/.claude/rules/` | T0 global | — | 2 283 | 0,6k |
| dotfiles/grok `*.md` | T0 global | — | 4 561 | 1,2k |
| **Tout .md repos propres (upper bound)** | — | **3 369** | **31 924 979** | **~8,6M** |

Domaines futurs :

| Corpus | Fichiers | Octets | ≈ tokens |
|---|---|---|---|
| silex-hub vault | 2 362 | 22 611 525 | ~6M |
| gosilex code repos (hors hub) | — | 13 872 925 | ~3,7M |

Conclusions (→ A1 acté) :

- Total ~68 MB de markdown = microscopique pour une DB → **fichiers+git SSoT trivialement viable**
- T2 (le cœur du débat D1-natif vs fichiers) = **99 KB** → aucun argument volume pour une DB
- ~5,7k fichiers tous domaines = bord haut de la zone « FTS suffit » (doctrine silex 2-10k) — l'argument Vectorize v1 est le **bilingue FR/EN** (paraphrase cross-langue), pas le volume
- Reste .md hors docs/artifacts/criticals ≈ 2 250 fichiers / 20 MB = skills, changelogs, misc — majoritairement « faire » (P7, hors memory)
