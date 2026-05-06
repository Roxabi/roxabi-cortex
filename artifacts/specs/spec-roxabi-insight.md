---
title: "roxabi-insight — Behavioral Observability for Claude Code Transcripts"
description: Unified behavioral + memory system — 3 source lanes (JSONL + git/gh + NATS), 4-layer architecture (Raw → Graph → Compiled Truth → Actuation), heuristic-driven episode analysis, optional LLM narrative, DuckDB substrate. Surfaces recurring behavioral patterns; absorbs lyra memory design to drive CLAUDE.md / memory / skill improvements.
status: superseded-partial
superseded_by: docs/adr/ — voir ADR-001..011 (2026-05-06)
---

> **⚠ SUPERSEDED PARTIELLEMENT (2026-05-06)** — Ce SP a guidé la phase de design jusqu'au 2026-05-05. Il a été partiellement superseded par la révision architecturale du 2026-05-06 :
>
> - Le projet s'appelle désormais **roxabi-cortex** (ADR-001) avec 2 services : cortex-insight (lake + ETL) et cortex-memory (warehouse + consolidation)
> - Découpage **lake/warehouse** au lieu de fusion (ADR-003)
> - Producteurs externes → insight uniquement (ADR-004)
> - Frontière insight/memory = contrat **`Observation`** typée (ADR-005)
> - Containerisé **Podman + Quadlet** (ADR-002), **monorepo workspace** (ADR-008)
> - DuckDB v1 conditionnel · KuzuDB cible si triggers (ADR-011)
> - 3 décisions ouvertes/déférées : ADR-007, ADR-009 (taxonomie), ADR-010 (cohabitation Lyra)
>
> **À ce stade :**
> - Vue d'ensemble à jour : `docs/ARCHITECTURE.md`
> - Décisions à jour : `docs/adr/`
> - Contenu de ce SP encore valide pour : détecteurs D1-D15 (pseudocode), outcome classifier (8 états), intent taxonomy (20 valeurs), sanitization tiers, segmentation algorithm, calibration protocol, breadboard slices V1-V7
> - Contenu de ce SP **obsolète** pour : nom projet · architecture global · contrat publish · découpage du repo · forme de déploiement · schéma `events` (JSONL-centric à généraliser)
>
> **Migration prévue** : scinder en `spec-cortex-insight.md` (parsers + pipelines + observations) et `spec-cortex-memory.md` (graphe + consolidation + assemble + actuate) après ADR-009 (taxonomie) résolue.

## Context

6 weeks of Claude Code sessions across ~15 Roxabi projects, ~5,657 `.jsonl` files (~1.5 GB) at `~/.claude/projects/`. Manual PR audit (#975–#1013, #1036) surfaced 7 upstream root causes (RC-1…RC-7) documented in lyra memory. Those RCs were extracted by hand — this tool makes that extraction systematic, repeatable, and retroactive.

Every detector in this spec maps explicitly to ≥1 RC or proposal-class (Ci = code pattern, Si = structural, Ui = user-behavior, proposal-letter).

**Promoted from:** manual audit + grilling session (2026-05-05, lyra memory `project_recurring_bug_classes.md`)

---

## Goal

Produce a ranked, actionable behavioral report per time window:
- Which patterns recur? (by frequency × severity × actionability)
- Are patterns improving week-over-week?
- Which episode clusters are automation candidates?
- What remediation type applies (CLAUDE.md edit / new skill / memory entry / allowlist)?

---

## Users & Use Cases

**Primary user:** Mickael (solo dev, heavy Claude Code usage across ~15 projects).

| Use case | Trigger | Output |
|----------|---------|--------|
| Weekly behavioral review | `insight report --since 7d` | ranked findings + calibration appendix |
| Retroactive audit (6-week corpus) | `insight ingest --since 2025-03-24` | full baseline |
| Before/after CLAUDE.md change | `insight compare WEEK1 WEEK2` | delta on all metrics |
| Identify automation candidates | `insight automation` | cluster report + suggested skill names |
| Calibrate new detector | `insight calibrate --sample-size 50` | P/R per detector |
| Spot-check a specific episode | `insight detect --episodes-only` | single-episode findings |

---

## Architecture Overview

### 7-Stage Pipeline

> **Scope:** This pipeline applies to Lane 1 (JSONL) only. See "3-Lane Architecture" section below for the full system.

```
  [1]           [2]          [3]          [4]         [5]         [6]           [7]
raw JSONL  →  sanitize  →  de-noise  →  segment  →  features  →  detect  →  DuckDB  →  report
               + regex        + trunc     (episode)   + enrich      D1-D15       ↑
                                                          ↑                  calibration
               ↓                                         |                    loop
         multi-source join: git log + gh PR/CI/issues ──┘
```

Stage notes:
- Stages 1-3 = single streaming pass per file (no second read of raw data).
- Stage 4 (segment) = stateful; consumes de-noised event stream.
- Stage 5 (features) = per-episode enrichment from SQLite + git/gh side-channels.
- Stage 6 (detect) = pure reads against `episodes` + `events` tables.
- LLM analyst (Phase 2 only) = optional overlay between detect and report; ¬primary judge.
- Calibration loop feeds back into detector thresholds (stored in `metrics`).

### Process topology

```
insight ingest          → stages 1-4 → SQLite (episodes + events + sanitization_log)
insight detect          → stage 5-6 → SQLite (findings)
insight classify        → outcome classifier → SQLite (episodes.outcome updated)
insight report          → read SQLite → render md|html|json
insight compare W1 W2   → read SQLite → delta report
insight automation      → read SQLite (findings D15) → cluster report
insight calibrate       → stratified sample → LLM bootstrap → P/R update
insight watch           → continuous mode (cocoindex Lane1+2 + NATS Lane3, all lanes live)
```

---

## 3-Lane Architecture

Three ingestion lanes feed a shared DuckDB store via cocoindex (incremental, delta-only).

### Lanes

| Lane | Source | Method | Entity types produced |
|------|--------|--------|-----------------------|
| 1 — JSONL | `~/.claude/projects/*.jsonl` | cocoindex batch + watch | Behavioral: Detector, RC, Pattern, Episode, Outcome |
| 2 — Git/GitHub | `git log` + `gh` API | Periodic batch (Lane 2 ingest) | Project, Outcome (PR/CI signals) |
| 3 — NATS | Lyra NATS bus | Real-time subscriber (`nats_adapter.py`) | LlmCall, Job, Turn, ConversationTurn |

### System-level pipeline

```
Lane 1 (JSONL)       Lane 2 (git/gh)      Lane 3 (NATS)
     │                      │                    │
     │ cocoindex             │ periodic batch     │ nats-py subscriber
     │ (delta-only,          │                    │ ContractEnvelope
     │ input_hash⊕code_hash) │                    │ typed subjects
     └──────────────────────┴────────────────────┘
                             │
                    [Layer 1 — Raw: events table]
                    (lane, nats_subject, trace_id columns)
                             │
                    Retain Job (event-triggered, heuristic)
                             │
                    [Layer 2 — Knowledge Graph]
                    entities + relations + decay
                             │
                    Impact Analysis + nightly consolidation
                             │
                    [Layer 3 — Compiled Truth]
                    per-entity markdown, regenerated nightly
                             │
                    approval queue (human gate)
                             │
                    [Layer 4 — Actuation]
                    CLAUDE.md / skill / memory PRs
```

JSONL-lane behavioral analysis (D1-D15, outcome classifier) feeds Layer 2 behavioral entities only.

### NATS subjects

`roxabi-contracts` (`lyra/packages/roxabi-contracts/`) provides the typed Pydantic `ContractEnvelope` base and subject literals. `nats_adapter.py` subscribes to subjects and deserializes using the contracts package.

**Dependency:**
```toml
[tool.uv.sources]
roxabi-contracts = { git = "https://github.com/Roxabi/lyra.git", subdirectory = "packages/roxabi-contracts", branch = "main" }
```

| Subject pattern | Status | Entity type produced |
|-----------------|--------|----------------------|
| `lyra.jobs.*` | Existing contract | Job |
| `lyra.results.*` | Existing contract | Job (result) |
| `lyra.progress.*` | Existing contract | Job (progress) |
| `lyra.llm.generate.*` | Existing contract | LlmCall |
| `lyra.voice.*` | Existing contract (`lyra.voice.tts.request`, `lyra.voice.stt.request`) | (observability only) |
| `lyra.image.*` | Existing contract | (observability only) |
| `lyra.conversation.>` | **Missing — needs new ADR in lyra (Q17)** | Turn, ConversationTurnEvent |
| `lyra.memory.*` | **Missing — needs new ADR in lyra (Q18)** | MemoryInsightEvent, MemoryQueryRequest/Response, MemoryReinforceEvent |

---

## 4-Layer Memory Architecture

Insight absorbs the lyra-memory design. One project, not two.

### Layer 1 — Raw (immutable, append-only)

DuckDB `events` table extended with:
- `lane VARCHAR DEFAULT 'jsonl'` — source lane identifier
- `nats_subject VARCHAR` — populated for `lane='nats'`
- `trace_id VARCHAR` — `ContractEnvelope.trace_id` for cross-lane correlation

Invariant: rows are never updated, only appended. Derived tables (graph, compiled) are regenerated from raw on schema change.

### Layer 2 — Knowledge Graph

Entities + relations with temporal decay. Schema in `docs/DATA-MODEL.md` section 2.9.

**Entity types:**
- Behavioral: Detector, RC, Pattern, Episode, Outcome
- World: Project, Person, Concept, Decision
- Instruction: CLAUDEmd-section, MemoryEntry, Skill, Allowlist
- NATS-derived: LlmCall, Job, Turn

**Relation types:** `fires_in`, `maps_to`, `co_occurs`, `remediated_by`, `supersedes`, `triggered_by`, `resulted_in`, `uses_model`, `costs`, `decided_in`, `reinforces`

**Decay formula:** `weight_temporal = exp(-Δt/σ)` where σ per entity class:
- Behavioral (detectors, RCs, patterns): σ = 30 days
- World (projects, persons, decisions): σ = 90 days
- Instruction (CLAUDE.md sections, skills): σ = 60 days

`memory_strength` reinforces on access; decays passively. Entity resolution: cosine > 0.85 auto-merge (Q19).

### Layer 3 — Compiled Truth

Per-entity markdown, regenerated nightly via impact analysis. `compiled/impact.py` determines which entities changed (Δ`memory_strength` > `regen_threshold`). `compiled/truth.py` regenerates body_md for affected entities. Versions are retained; `superseded_by` FK chains the history.

Config: `regen_threshold = 0.1` (10% memory_strength change triggers regen).

### Layer 4 — Actuation

Approval queue + auto-PR. Human gate before any CLAUDE.md/skill/memory diff lands.

1. `compiled/truth.py` emits diff → `approval_queue` row (status=pending)
2. `insight memory approve` lists pending; user approves/rejects
3. `insight memory publish` — approved items → `actuate/pr.py` → auto-PR on target repo
4. Config: `auto_pr = false` (explicit publish required)

---

## Memory Strength Model

Adapted from hippo-memory (biologically-inspired). Replaces the bare `exp(-Δt/σ)` formula.

### Strength formula

```
strength(t) = base_strength
              × (0.5 ^ (Δt / effective_half_life))
              × retrieval_boost
              × emotional_multiplier

where:
  Δt                  = days since last_reinforced
  reward_factor       = 1 + 0.5 × ((outcome_pos - outcome_neg) / (outcome_pos + outcome_neg + 1))
                        range: (0.5, 1.5)
  effective_half_life = half_life_days × reward_factor
  retrieval_boost     = 1 + (0.1 × log₂(retrieval_count + 1))
  emotional_multiplier = neutral:1.0 | positive:1.3 | negative:1.5 | critical:2.0
```

### Severity → emotional_valence mapping

| Finding severity | emotional_valence | Multiplier | Effect |
|---|---|---|---|
| high | critical | 2.0 | Half-life doubled at base; entity persists much longer |
| medium | negative | 1.5 | Half-life ×1.5 |
| low | neutral | 1.0 | Nominal decay |

### Half-life adjustment table

| Signal | Modifier |
|---|---|
| Each query of entity (`retrieval_count++`) | +2d base half-life (via retrieval_boost) |
| `emotional_valence=critical` | ×2.0 base half-life |
| `schema_fit > 0.7` (known RC — fast-track) | ×1.5 (consolidates quickly) |
| `schema_fit < 0.3` (novel — dark matter bucket) | ×0.5 (fades fast if unused) |
| `outcome_positive` chain → adoption rate ≥ 0.7 | `reward_factor` up to 1.5× |
| `outcome_negative` chain → no improvement post-merge | `reward_factor` down to 0.5× |
| `pinned = TRUE` (user locked) | Infinite — no decay |

### Decay basis modes

| Mode | When to use |
|---|---|
| `clock` | Wall-clock time; simple, predictable |
| `session` | Decay by sleep-cycle count; for intermittent project use |
| `adaptive` | Scale half-life by avg session interval per project (default) |

`adaptive` is the default: projects Mickael opens daily decay at nominal rate; projects opened monthly auto-extend half-life ×30. No per-project config needed.

### Schema fit

Computed at Retain Job time (heuristic, no LLM). IDF-weighted tag Jaccard + content token overlap against existing entities.

| schema_fit range | Routing | Effect |
|---|---|---|
| > 0.7 | Known RC / known pattern | Fast-track to compiled truth; half-life ×1.5 |
| 0.3 – 0.7 | Moderate fit | Normal consolidation |
| < 0.3 | Dark matter (no matching RC) | half-life ×0.5; survives only via high strength; LLM mines survivors in Phase 2 |

### Reward feedback loop (closes the actuation cycle)

```
finding fires (RC-2) → entity.outcome_positive++  (if CLAUDE.md edit merged + pattern rate ↓)
                      → entity.outcome_negative++  (if pattern rate unchanged after merge)
→ reward_factor modulates effective_half_life
→ RC-2 that was successfully remediated decays slower (stays prominent)
→ RC-2 where remediation had no effect decays faster (self-correcting signal)
```

### Memory kind envelope

Every `findings` row and every `compiled_truth` row carries:

| kind | Meaning | Lifecycle |
|---|---|---|
| `raw` | Detector finding — append-only | Never directly deleted; archive via `suppress=TRUE` → kind→`archived` |
| `distilled` | Compiled truth body (synthesized) | Regenerated nightly; previous version → `superseded` |
| `superseded` | Replaced compiled truth version | Retained for trend analysis; linked via `superseded_by` |
| `archived` | Suppressed by user (calibration) or GDPR delete | Removed from FTS; raw_archive snapshot kept |

### Conflict detection

Run during compiled truth generation and before approval queue promotion.

Algorithm (hippo-adapted):
1. Stopword-filter both entity bodies.
2. Compute Jaccard on remaining tokens.
3. Check polarity heuristics on first 40 words (explicit negation).
4. If Jaccard > 0.5 AND polarity conflict → mark `conflicts_with` on both entities.
5. Conflicting approval queue entries are flagged; human must resolve before merge.

### Correction latency

Self-metric for the actuation layer:

```
correction_latency = approval_queue.decided_at − finding.created_at
```

Surface in weekly digest. Persistent high latency (> 14d) on HIGH severity findings → system health warning.

---

## Data Model

> **Note:** Full schema (DuckDB) in `docs/DATA-MODEL.md` — authoritative. The SQLite schema below is superseded by the DuckDB schema in DATA-MODEL.md. Retained here as a reference for detector pseudocode and episode field documentation.

### SQLite Schema (SUPERSEDED — see DATA-MODEL.md)

> Implementation note: use `sqlite-utils` for schema management. All timestamps = ISO-8601 UTC strings. FKs enforced (`PRAGMA foreign_keys = ON`).
> **Storage is DuckDB (locked, Q13). Schema below marked `-- SUPERSEDED: see DATA-MODEL.md` on each table.**

```sql
-- ──────────────────────────────────────────────
-- episodes: one row per logical task episode
-- ──────────────────────────────────────────────
CREATE TABLE episodes (
    id                   TEXT PRIMARY KEY,          -- sha256(project + branch + started_at)[:16]
    project              TEXT NOT NULL,             -- e.g. "lyra", "imageCLI", "roxabi-forge"
    intent               TEXT NOT NULL,             -- see intent taxonomy (20 values)
    started_at           TEXT NOT NULL,             -- ISO-8601 UTC
    ended_at             TEXT,                      -- NULL = open/PENDING
    git_branch           TEXT,
    cwd                  TEXT,                      -- normalized (~/ prefix)
    orchestrator_skill   TEXT,                      -- e.g. "dev-core:dev", "dev-core:fix"
    outcome              TEXT DEFAULT 'PENDING',    -- 8-state enum (see Outcome section)
    files_touched_count  INTEGER DEFAULT 0,
    token_estimate       INTEGER DEFAULT 0,
    user_correction_count INTEGER DEFAULT 0,
    sub_agent_count      INTEGER DEFAULT 0,
    pr_number            INTEGER,                   -- linked PR (nullable)
    issue_number         INTEGER,                   -- linked issue (nullable)
    session_ids          TEXT,                      -- JSON array of constituent session IDs
    source_tool_use_id   TEXT,                      -- parent span if subagent
    classified_at        TEXT,                      -- when outcome was last set
    outcome_signals      TEXT                       -- JSON: which signals drove classification
);

CREATE INDEX idx_episodes_project   ON episodes(project);
CREATE INDEX idx_episodes_intent    ON episodes(intent);
CREATE INDEX idx_episodes_outcome   ON episodes(outcome);
CREATE INDEX idx_episodes_started   ON episodes(started_at);
CREATE INDEX idx_episodes_pr        ON episodes(pr_number);
CREATE INDEX idx_episodes_branch    ON episodes(git_branch);

-- ──────────────────────────────────────────────
-- events: de-noised tool calls + user turns
-- ──────────────────────────────────────────────
CREATE TABLE events (
    id              TEXT PRIMARY KEY,       -- sha256(session_id + turn_index + tool_use_id)[:20]
    episode_id      TEXT NOT NULL REFERENCES episodes(id),
    session_id      TEXT NOT NULL,          -- raw JSONL source session ID
    turn_index      INTEGER NOT NULL,
    event_type      TEXT NOT NULL,          -- "tool_use" | "tool_result" | "user_turn" | "assistant_turn"
    tool_name       TEXT,                   -- "Read" | "Edit" | "Bash" | "Write" | etc.
    tool_args       TEXT,                   -- JSON (sanitized)
    tool_result     TEXT,                   -- truncated (per de-noise rules) + sanitized
    exit_code       INTEGER,                -- Bash only
    is_error        INTEGER DEFAULT 0,      -- 1 if error string detected in result
    content_hash    TEXT,                   -- SHA256 of original tool_result (pre-truncation)
    source_file     TEXT NOT NULL,          -- path to origin .jsonl file
    source_offset   INTEGER NOT NULL,       -- byte offset in source file (fallback anchor)
    ts              TEXT                    -- ISO-8601 if available in JSONL
);

CREATE INDEX idx_events_episode  ON events(episode_id);
CREATE INDEX idx_events_session  ON events(session_id);
CREATE INDEX idx_events_tool     ON events(tool_name);
CREATE INDEX idx_events_error    ON events(is_error);

-- ──────────────────────────────────────────────
-- metrics: per-episode aggregate features
-- ──────────────────────────────────────────────
CREATE TABLE metrics (
    episode_id          TEXT PRIMARY KEY REFERENCES episodes(id),
    tool_call_count     INTEGER DEFAULT 0,
    edit_count          INTEGER DEFAULT 0,
    read_count          INTEGER DEFAULT 0,
    bash_count          INTEGER DEFAULT 0,
    error_count         INTEGER DEFAULT 0,
    truncation_count    INTEGER DEFAULT 0,
    retry_sequences     INTEGER DEFAULT 0,   -- count of D1-triggering runs
    ctx_token_estimate  INTEGER DEFAULT 0,
    session_count       INTEGER DEFAULT 0,
    intent_token_median INTEGER,             -- populated by calibrate; median for intent class
    computed_at         TEXT
);

-- ──────────────────────────────────────────────
-- findings: one row per detector hit per episode
-- ──────────────────────────────────────────────
CREATE TABLE findings (
    id              TEXT PRIMARY KEY,           -- sha256(episode_id + detector_id)[:16]
    episode_id      TEXT NOT NULL REFERENCES episodes(id),
    detector_id     TEXT NOT NULL,              -- "D1" … "D15"
    severity        TEXT NOT NULL,              -- "high" | "medium" | "low"
    evidence        TEXT,                       -- JSON: key fields that triggered
    example_turns   TEXT,                       -- JSON array of event IDs (≤3)
    remediation     TEXT,                       -- "CLAUDE.md" | "new-skill" | "memory" | "allowlist"
    rc_mapping      TEXT,                       -- "RC-2" | "RC-7" | etc.
    detected_at     TEXT NOT NULL,
    suppressed      INTEGER DEFAULT 0           -- 1 = user marked invalid during calibration
);

CREATE INDEX idx_findings_episode   ON findings(episode_id);
CREATE INDEX idx_findings_detector  ON findings(detector_id);
CREATE INDEX idx_findings_rc        ON findings(rc_mapping);

-- ──────────────────────────────────────────────
-- patterns: D15 automation clusters
-- ──────────────────────────────────────────────
CREATE TABLE patterns (
    id                   TEXT PRIMARY KEY,
    skill_sequence_sig   TEXT NOT NULL,      -- canonical serialization of skill sequence
    file_glob_pattern    TEXT,               -- e.g. "src/lyra/**/*.py"
    cluster_size         INTEGER NOT NULL,
    success_rate         REAL NOT NULL,      -- 0.0-1.0
    step_sequence_stable INTEGER NOT NULL,   -- 0|1
    suggested_skill_name TEXT,
    suggested_steps      TEXT,               -- JSON array
    first_seen           TEXT,
    last_seen            TEXT,
    computed_at          TEXT
);

-- ──────────────────────────────────────────────
-- pr_state: GitHub PR metadata for D9/D10/outcome
-- ──────────────────────────────────────────────
CREATE TABLE pr_state (
    pr_number       INTEGER PRIMARY KEY,
    repo            TEXT NOT NULL,           -- "Roxabi/lyra"
    head_ref        TEXT,
    state           TEXT,                    -- "open" | "merged" | "closed"
    review_iter_count INTEGER DEFAULT 0,
    has_unresolved_blockers INTEGER DEFAULT 0,
    ci_green        INTEGER,                 -- 0|1|NULL
    merged_at       TEXT,
    closed_at       TEXT,
    labels          TEXT,                    -- JSON array
    fetched_at      TEXT NOT NULL
);

CREATE INDEX idx_pr_state_head ON pr_state(head_ref);

-- ──────────────────────────────────────────────
-- git_events: commits + rollbacks
-- ──────────────────────────────────────────────
CREATE TABLE git_events (
    id          TEXT PRIMARY KEY,        -- sha
    project     TEXT NOT NULL,
    branch      TEXT,
    message     TEXT,
    author      TEXT,
    committed_at TEXT NOT NULL,
    is_revert   INTEGER DEFAULT 0,       -- 1 if "revert" in message
    files_changed INTEGER,
    episode_id  TEXT REFERENCES episodes(id)
);

CREATE INDEX idx_git_events_branch   ON git_events(branch);
CREATE INDEX idx_git_events_episode  ON git_events(episode_id);

-- ──────────────────────────────────────────────
-- issue_events: GitHub issue state changes
-- ──────────────────────────────────────────────
CREATE TABLE issue_events (
    id          TEXT PRIMARY KEY,
    issue_number INTEGER NOT NULL,
    repo        TEXT NOT NULL,
    event_type  TEXT,                    -- "closed" | "labeled" | "reopened" | etc.
    actor       TEXT,
    created_at  TEXT NOT NULL,
    episode_id  TEXT REFERENCES episodes(id)
);

CREATE INDEX idx_issue_events_issue   ON issue_events(issue_number);
CREATE INDEX idx_issue_events_episode ON issue_events(episode_id);

-- ──────────────────────────────────────────────
-- sanitization_log: trufflehog + regex redaction audit
-- ──────────────────────────────────────────────
CREATE TABLE sanitization_log (
    id              TEXT PRIMARY KEY,
    source_file     TEXT NOT NULL,
    source_offset   INTEGER NOT NULL,
    redaction_type  TEXT NOT NULL,       -- "T1_API_KEY" | "T1_JWT" | "T1_BOT_TOKEN" | etc.
    detector        TEXT NOT NULL,       -- "trufflehog" | "regex:<pattern_name>" | "entropy"
    redacted_to     TEXT NOT NULL,       -- e.g. "<REDACTED:API_KEY>"
    processed_at    TEXT NOT NULL
);

CREATE INDEX idx_san_log_file ON sanitization_log(source_file);
```

---

## Sanitization Pass

Runs in-stream (stage 2). No second read of raw data.

### Tool

`trufflehog filesystem <path> --no-verification --json` at path = `~/.claude/projects/`.
Binary: `/home/mickael/.local/bin/trufflehog`.
`--no-verification` is mandatory — verification mode attempts detected tokens against live APIs, which is dangerous by design.

### Redaction tiers

| Tier | Type | Treatment | Tag |
|------|------|-----------|-----|
| T1 (must) | API keys (OpenAI, Anthropic, AWS, GCP) | Redact | `<REDACTED:API_KEY>` |
| T1 (must) | JWTs | Redact | `<REDACTED:JWT>` |
| T1 (must) | Bearer tokens | Redact | `<REDACTED:BEARER>` |
| T1 (must) | Telegram bot tokens | Redact | `<REDACTED:BOT_TOKEN>` |
| T1 (must) | Discord tokens | Redact | `<REDACTED:DISCORD_TOKEN>` |
| T1 (must) | NATS NKEYs | Redact | `<REDACTED:NKEY>` |
| T1 (must) | DB URIs with embedded creds | Redact | `<REDACTED:DB_URI>` |
| T1 (must) | SSH private keys | Redact | `<REDACTED:SSH_KEY>` |
| T2 (recommended) | Email addresses | Normalize | `<REDACTED:EMAIL>` |
| T2 (recommended) | IP addresses | Normalize | `<REDACTED:IP>` |
| T2 (recommended) | MAC addresses | Normalize | `<REDACTED:MAC>` |
| T2 (recommended) | `/home/mickael` in paths | Normalize | `~` |
| T3 (keep) | Project names (lyra, roxabi-\*) | Keep | — |
| T3 (keep) | File paths under `~/projects/` | Keep | — |
| T3 (keep) | Issue/PR numbers | Keep | — |
| T3 (keep) | Git branches | Keep | — |
| T3 (keep) | Plugin/skill names | Keep | — |
| T4 (keep) | GitHub usernames, "Mickael" | Keep | — |

### Fallback layers (applied after trufflehog, in order)

1. Regex layer: patterns for Telegram (`\d{8,10}:[A-Za-z0-9_-]{35}`), NATS NKEYs (`^[SU][A-Z2-7]{56}$`), AWS (`AKIA[0-9A-Z]{16}`), JWTs (`eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`), bearer (`(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}`), Discord (`[MNO][A-Za-z0-9_-]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}`), Anthropic (`sk-ant-[A-Za-z0-9\-]{40,}`), OpenAI (`sk-[A-Za-z0-9]{48}`).
2. Shannon entropy fallback: base64-shaped strings (alphabet `[A-Za-z0-9+/=]`, length ≥20) with H > 4.5 bits/char → `<REDACTED:HIGH_ENTROPY>`.

### Truncation anchor (load-bearing for LLM analyst fallback)

Every truncated span in `events.tool_result` carries inline metadata:

```
<TRUNCATED source_file="~/.claude/projects/lyra/abc123.jsonl" offset=1048576 original_hash="sha256:deadbeef" lines_total=1200 kept_head=50 kept_tail=50>
```

If LLM analyst flags an ambiguous span, raw content is retrievable via `(source_file, offset)`.

### Validation gates

After sanitization pass completes:
1. Re-run trufflehog on `~/.claude/analysis/sanitized/` → must return 0 findings.
2. 10-span manual spot-check (random sample from `sanitization_log`).
3. Determinism check: re-run sanitize on same input → diff of `sanitization_log` must be empty.

### Working corpus

Input: `~/.claude/projects/`
Output: `~/.claude/analysis/sanitized/` (sanitized + de-noised JSONL)

---

## De-Noising Pass

Runs in same stream as sanitization (stage 3).

### Dropped event types

| Type | Reason |
|------|--------|
| `permission-mode` | Infrastructure boilerplate, ¬signal |
| `ai-title` | Auto-generated, ¬intent signal |
| `last-prompt` | Duplicate of user turn |
| `hookInfos` | Internal hook metadata |

### Tool result truncation rules

| Tool | Keep | Drop |
|------|------|------|
| Read | path + line_range + file_size + first 10 lines + last 10 lines (if file < 200 lines) | file body |
| Bash | cmd + exit_code + stderr (full) + stdout head-50 + tail-50 if > 5 KB | middle of large stdout |
| Grep | query + match_count + first 10 matches | remaining matches |
| Glob | pattern + count + first 20 results | remaining results |
| Edit / Write | file + full diff | — (diffs are always signal) |
| WebFetch / WebSearch | URL + HTTP status + first 1 KB | remaining body |

**Exception (ALWAYS keep full result):** `exit_code != 0` OR any of: `error`, `Error`, `Exception`, `Traceback`, `command not found`, `No such file`, `ImportError`, `ModuleNotFoundError`, `AttributeError`, `is not defined`, `Permission denied`, `FAILED`, `AssertionError`. These are the primary signal for RC-2 and RC-7 detectors.

### Boilerplate dedup

CLAUDE.md / memory / system-reminder content → SHA256 hash → store once in `boilerplate.json` at `~/.claude/analysis/boilerplate.json` → replace inline occurrences with `<BOILERPLATE:sha256[:8]>`.

---

## Episode Segmentation

### Episode fields

```
Episode {
  id:                   TEXT   (sha256 of project+branch+started_at)
  project:              TEXT
  intent:               TEXT   (see taxonomy)
  started_at:           TEXT
  ended_at:             TEXT | NULL
  git_branch:           TEXT
  cwd:                  TEXT
  orchestrator_skill:   TEXT | NULL
  outcome:              TEXT   (default PENDING)
  files_touched_count:  INT
  token_estimate:       INT
  user_correction_count: INT
  sub_agent_count:      INT
  pr_number:            INT | NULL
  issue_number:         INT | NULL
  session_ids:          TEXT[] (JSON)
  source_tool_use_id:   TEXT | NULL
}
```

### Segmentation algorithm (pseudocode)

```python
def segment_episodes(events: Iterator[Event]) -> Iterator[Episode]:
    current: Episode | None = None
    orchestrator_active: bool = False
    orchestrator_stack: list[str] = []

    ORCHESTRATOR_SKILLS = {
        "dev-core:dev", "dev-core:fix", "dev-core:promote",
        "dev-core:cleanup-context", "dev-core:1b1", "dev-core:loop"
    }
    IDLE_GAP_MINUTES = 30  # tunable; disabled by default (config.idle_gap_enabled = False)

    for event in events:
        # Detect orchestrator skill activation
        if event.event_type == "skill_attribution":
            if event.skill_name in ORCHESTRATOR_SKILLS:
                # New orchestrator → close current episode, open new
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)
                orchestrator_active = True
                orchestrator_stack = [event.skill_name]
            elif orchestrator_active:
                # Sub-skill inside orchestrator → absorb, do NOT boundary
                pass
            else:
                # Non-orchestrator skill change without active orchestrator → boundary
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)

        elif event.event_type in ("branch_change", "cwd_change"):
            if orchestrator_active:
                # Absorb — dev-core:dev opens fresh sessions per task; still one episode
                current.git_branch = event.new_value if event.event_type == "branch_change" else current.git_branch
                current.cwd = event.new_value if event.event_type == "cwd_change" else current.cwd
            else:
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)

        elif event.event_type == "session_start":
            if can_merge(current, event):
                # Same branch + same cwd + active orchestrator → merge into current
                current.session_ids.append(event.session_id)
            else:
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)

        elif event.event_type == "subagent_start":
            current.sub_agent_count += 1
            # Subagent sessions linked via source_tool_use_id; processed as own episodes
            # but attributed back to parent via source_tool_use_id FK

        else:
            # Normal event → accumulate into current episode
            accumulate(current, event)

        # Idle gap boundary (only if config.idle_gap_enabled)
        if config.idle_gap_enabled and current is not None:
            if gap_minutes(current.last_event_ts, event.ts) > IDLE_GAP_MINUTES:
                yield finalize(current)
                current = new_episode(event)

    if current is not None:
        yield finalize(current)


def can_merge(current: Episode | None, session_start: Event) -> bool:
    if current is None:
        return False
    return (
        session_start.git_branch == current.git_branch
        and session_start.cwd == current.cwd
        and current.orchestrator_skill is not None  # active orchestrator
        and gap_minutes(current.last_event_ts, session_start.ts) < MERGE_WINDOW_MINUTES
    )
```

Key invariant: **when orchestrator is active, branch/cwd switches do NOT close the episode.** Mickael's `/dev #N` flow opens fresh sessions per phase (frame/spec/plan/implement) but is one logical episode.

LLM segmenter (Phase 2 only): processes residue spans where `can_merge` is ambiguous (branch mismatch + no active orchestrator + gap < 60 min).

---

## Intent Taxonomy

20 intents. Auto-classification from `attributionSkill` field in JSONL (present in ≥80% of sessions). Freeform is the only bucket requiring LLM residue classifier.

| Intent | Source signal | Skill / branch pattern |
|--------|--------------|----------------------|
| `dev-lifecycle` | `attributionSkill = "dev-core:dev"` | — |
| `frame` | `attributionSkill = "dev-core:frame"` | — |
| `analyze` | `attributionSkill = "dev-core:analyze"` | — |
| `spec` | `attributionSkill = "dev-core:spec"` | — |
| `plan` | `attributionSkill = "dev-core:plan"` | — |
| `implement-feature` | `attributionSkill = "dev-core:implement"` + branch !~ `fix\|bug\|patch` | — |
| `implement-bugfix` | `attributionSkill = "dev-core:implement"` + branch ~= `fix\|bug\|patch` | — |
| `code-review` | `attributionSkill = "dev-core:code-review"` | — |
| `fix-findings` | `attributionSkill = "dev-core:fix"` | — |
| `pr` | `attributionSkill = "dev-core:pr"` | — |
| `promote` | `attributionSkill = "dev-core:promote"` | — |
| `triage` | `attributionSkill ~ "dev-core:issue-triage\|dev-core:issues"` | — |
| `interview` | `attributionSkill = "dev-core:interview"` | — |
| `validate` | `attributionSkill = "dev-core:validate"` | — |
| `refactor` | branch ~= `refactor\|extract\|split\|move` | any |
| `ops-debug` | `attributionSkill = "lyra-ops:lyra-debug"` | — |
| `forge-create` | `attributionSkill ~= "forge:.*"` | — |
| `vault-ops` | `attributionSkill ~= "roxabi-vault:.*"` | — |
| `research` | `attributionSkill ~= "web-intel:.*"` | — |
| `cleanup` | `attributionSkill ~= "dev-core:cleanup.*"` | — |
| `freeform` | all other (catch-all) | LLM residue classifier (Phase 2) |

---

## Outcome Classifier

### 8-State Enum

| Outcome | Definition |
|---------|-----------|
| `SUCCESS_CLEAN` | CI green + ≤1 review iter + no rollback in 2-week window + no prod issue |
| `SUCCESS_PIVOT` | ADR supersession with positive framing (design changed for the better) |
| `PARTIAL_REVIEW_LOOPS` | Succeeded but >1 review iter |
| `PARTIAL_PROD_ISSUES` | Succeeded but small prod issue followed |
| `PARTIAL_DESIGN_THRASH` | Converged but heavy spec/ADR back-and-forth |
| `FAILED_LOOPS` | Hit 3-iter review cap with unresolved blockers (RC-5 signal) |
| `FAILED_PROD_NIGHTMARE` | Prod incident + multiple rollbacks |
| `PENDING` | < 12h after `episode.ended_at` |

### Signal sources

| Signal | Source | Maps to |
|--------|--------|---------|
| CI result | `pr_state.ci_green` | SUCCESS vs PARTIAL/FAILED |
| Review iter count | `pr_state.review_iter_count` | PARTIAL_REVIEW_LOOPS / FAILED_LOOPS |
| Unresolved blockers at merge | `pr_state.has_unresolved_blockers` | FAILED_LOOPS |
| Revert commit on branch | `git_events.is_revert` in lookahead window | FAILED_PROD_NIGHTMARE |
| Issue re-opened after close | `issue_events.event_type = "reopened"` | PARTIAL_PROD_ISSUES |
| ADR supersession + positive label | `git_events.message ~= "supersede.*ADR"` | SUCCESS_PIVOT |
| No PR linked | episode outcome derivable from git only | SUCCESS_CLEAN (heuristic) |

### Classification algorithm

```python
def classify_outcome(episode: Episode, db: Store) -> str:
    if not episode.ended_at or hours_since(episode.ended_at) < 12:
        return "PENDING"

    pr = db.get_pr(episode.pr_number)
    commits = db.get_git_events(episode_id=episode.id)
    issues = db.get_issue_events(episode_id=episode.id)

    # FAILED
    if pr and pr.has_unresolved_blockers and pr.review_iter_count >= 3:
        return "FAILED_LOOPS"
    reverts = [c for c in commits if c.is_revert]
    if len(reverts) >= 2:
        return "FAILED_PROD_NIGHTMARE"
    reopened = [e for e in issues if e.event_type == "reopened"]
    if len(reverts) >= 1 and reopened:
        return "FAILED_PROD_NIGHTMARE"

    # PARTIAL
    if pr and pr.review_iter_count > 1:
        return "PARTIAL_REVIEW_LOOPS"
    if reverts:
        return "PARTIAL_PROD_ISSUES"
    if reopened:
        return "PARTIAL_PROD_ISSUES"

    # SUCCESS
    if any("supersede" in c.message.lower() for c in commits):
        return "SUCCESS_PIVOT"
    return "SUCCESS_CLEAN"
```

### Nightly re-classification

Cron job (or `insight classify --rerun`): re-evaluate PENDING + SUCCESS episodes where:
- `git_events.is_revert` arrived after initial classification.
- `pr_state.review_iter_count` incremented.
- `issue_events.event_type = "reopened"` arrived.

---

## Detector Pack v1

### Tier A — Regex + Counters (D1–D8)

All run against `events` and `metrics` tables.

---

**D1 `retry_loop`** → RC-5 / S3 / proposal-C
Severity: high | Remediation: CLAUDE.md

```python
def D1(episode_id: str, db: Store) -> Finding | None:
    events = db.get_tool_events(episode_id)
    window = []
    for evt in events:
        sig = tool_signature(evt)  # (tool_name, args_hash)
        if window and window[-1].sig == sig:
            window.append(evt)
        else:
            window = [evt]
        if len(window) >= 3:
            # Check no result delta between consecutive calls
            results = [e.tool_result_hash for e in window]
            if len(set(results)) == 1:  # identical results
                return Finding(
                    detector_id="D1",
                    evidence={"tool": evt.tool_name, "repetitions": len(window), "sig": sig},
                    example_turns=[e.id for e in window[:3]],
                    rc_mapping="RC-5",
                    severity="high",
                    remediation="CLAUDE.md"
                )
    return None
```

---

**D2 `verification_gap`** → RC-7 / C1 / C2
Severity: high | Remediation: CLAUDE.md

```python
def D2(episode_id: str, db: Store) -> Finding | None:
    events = db.get_tool_events(episode_id)
    has_edit_or_write = any(e.tool_name in ("Edit", "Write") for e in events)
    if not has_edit_or_write:
        return None

    last_edit_idx = max(i for i, e in enumerate(events) if e.tool_name in ("Edit", "Write"))
    post_edit = events[last_edit_idx + 1:]

    VERIFY_PATTERNS = [
        ("Bash", r"pytest|uv run pytest|ruff|pyright|mypy|test"),
        ("Bash", r"make test|make lint|make typecheck"),
    ]
    for evt in post_edit:
        for tool, pattern in VERIFY_PATTERNS:
            if evt.tool_name == tool and re.search(pattern, evt.tool_args or ""):
                return None  # verification found

    return Finding(
        detector_id="D2",
        evidence={"last_edit_turn": last_edit_idx, "post_edit_event_count": len(post_edit)},
        example_turns=[events[last_edit_idx].id],
        rc_mapping="RC-7",
        severity="high",
        remediation="CLAUDE.md"
    )
```

---

**D3 `read_before_edit`** → RC-2 / proposal-A
Severity: medium | Remediation: CLAUDE.md

```python
def D3(episode_id: str, db: Store) -> Finding | None:
    events = db.get_tool_events(episode_id)
    files_edited: dict[str, int] = {}   # file → first Edit turn index
    files_read: dict[str, int] = {}     # file → first Read turn index

    for i, evt in enumerate(events):
        if evt.tool_name in ("Edit", "Write"):
            path = extract_path(evt.tool_args)
            if path and path not in files_edited:
                files_edited[path] = i
        elif evt.tool_name == "Read":
            path = extract_path(evt.tool_args)
            if path and path not in files_read:
                files_read[path] = i

    violations = []
    for path, edit_idx in files_edited.items():
        first_read = files_read.get(path)
        sibling_read = any(
            same_dir(path, rpath) and ridx < edit_idx
            for rpath, ridx in files_read.items()
        )
        if first_read is None or first_read > edit_idx:
            if not sibling_read:
                violations.append((path, edit_idx))

    if violations:
        return Finding(
            detector_id="D3",
            evidence={"unread_files_edited": [v[0] for v in violations[:5]]},
            example_turns=[events[v[1]].id for v in violations[:3]],
            rc_mapping="RC-2",
            severity="medium",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D4 `user_correction`** → U3
Severity: medium | Remediation: CLAUDE.md / memory

```python
CORRECTION_PATTERN = re.compile(
    r"\b(no|stop|don'?t|wrong|instead|not what|that'?s not|incorrect|undo|revert that)\b",
    re.IGNORECASE
)

def D4(episode_id: str, db: Store) -> Finding | None:
    events = db.get_events(episode_id, type="user_turn")
    corrections = [
        evt for evt in events
        if CORRECTION_PATTERN.search(evt.content or "")
        and word_count(evt.content) < 50
    ]
    if corrections:
        episode = db.get_episode(episode_id)
        db.update_episode(episode_id, user_correction_count=len(corrections))
        return Finding(
            detector_id="D4",
            evidence={"correction_count": len(corrections)},
            example_turns=[c.id for c in corrections[:3]],
            rc_mapping=None,
            severity="medium",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D5 `cost_outlier`** → S5
Severity: medium | Remediation: CLAUDE.md

```python
def D5(episode_id: str, db: Store) -> Finding | None:
    episode = db.get_episode(episode_id)
    metric = db.get_metrics(episode_id)
    # median populated during calibrate; skip if not yet computed
    if not metric.intent_token_median:
        return None
    if metric.ctx_token_estimate > 3 * metric.intent_token_median:
        return Finding(
            detector_id="D5",
            evidence={
                "token_estimate": metric.ctx_token_estimate,
                "intent_median": metric.intent_token_median,
                "ratio": round(metric.ctx_token_estimate / metric.intent_token_median, 1)
            },
            example_turns=[],
            rc_mapping=None,
            severity="medium",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D6 `ctx_pressure`** → S1
Severity: medium | Remediation: CLAUDE.md

```python
CTX_TOKEN_THRESHOLD = 150_000
TRUNCATION_PATTERN = re.compile(r"<TRUNCATED\s")

def D6(episode_id: str, db: Store) -> Finding | None:
    metric = db.get_metrics(episode_id)
    truncations = db.count_truncated_events(episode_id)

    if metric.ctx_token_estimate > CTX_TOKEN_THRESHOLD or truncations > 0:
        return Finding(
            detector_id="D6",
            evidence={
                "token_estimate": metric.ctx_token_estimate,
                "threshold": CTX_TOKEN_THRESHOLD,
                "truncation_count": truncations
            },
            example_turns=[],
            rc_mapping=None,
            severity="medium",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D7 `hallucinated_symbol`** → C8
Severity: high | Remediation: CLAUDE.md / memory

```python
HALLUCINATION_PATTERNS = re.compile(
    r"command not found|No such file or directory|ImportError|ModuleNotFoundError"
    r"|AttributeError|'[^']+' is not defined|NameError|cannot import name",
    re.IGNORECASE
)

def D7(episode_id: str, db: Store) -> Finding | None:
    error_events = db.get_error_events(episode_id)  # events.is_error = 1
    hallucination_hits = [
        evt for evt in error_events
        if HALLUCINATION_PATTERNS.search(evt.tool_result or "")
    ]
    if hallucination_hits:
        return Finding(
            detector_id="D7",
            evidence={"hit_count": len(hallucination_hits)},
            example_turns=[e.id for e in hallucination_hits[:3]],
            rc_mapping="RC-2",
            severity="high",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D8 `permission_friction`** → S2
Severity: low | Remediation: allowlist

```python
def D8(db: Store) -> list[Finding]:
    """Cross-episode detector — runs against all episodes in window."""
    sigs = db.query("""
        SELECT tool_name, tool_args_hash, COUNT(DISTINCT episode_id) as ep_count
        FROM events
        WHERE event_type = 'permission_prompt'
        GROUP BY tool_name, tool_args_hash
        HAVING ep_count >= 5
    """)
    return [
        Finding(
            detector_id="D8",
            evidence={"tool": row.tool_name, "signature": row.tool_args_hash, "episode_count": row.ep_count},
            example_turns=[],
            rc_mapping=None,
            severity="low",
            remediation="allowlist"
        )
        for row in sigs
    ]
```

---

### Tier B — Cross-Source (D9–D12)

Require `pr_state` + `git_events` tables populated.

---

**D9 `review_loop_cap`** → RC-5
Severity: high | Remediation: new-skill

```python
def D9(episode_id: str, db: Store) -> Finding | None:
    episode = db.get_episode(episode_id)
    if not episode.pr_number:
        return None
    pr = db.get_pr(episode.pr_number)
    if pr and pr.review_iter_count >= 3 and pr.has_unresolved_blockers:
        return Finding(
            detector_id="D9",
            evidence={"pr_number": pr.pr_number, "iter_count": pr.review_iter_count},
            example_turns=[],
            rc_mapping="RC-5",
            severity="high",
            remediation="new-skill"
        )
    return None
```

---

**D10 `fix_introduces_defects`** → RC-7
Severity: high | Remediation: CLAUDE.md

```python
def D10(db: Store) -> list[Finding]:
    """
    For each dev-core:fix episode followed by a dev-core:code-review episode
    on the same PR, check if the review found NEW findings not present in
    the prior review.
    """
    fix_episodes = db.get_episodes_by_intent("fix-findings")
    findings = []
    for fix_ep in fix_episodes:
        if not fix_ep.pr_number:
            continue
        review_eps = db.get_review_episodes_for_pr(fix_ep.pr_number, after=fix_ep.ended_at)
        for rev_ep in review_eps:
            prior_findings = db.get_findings_before(fix_ep.started_at, pr_number=fix_ep.pr_number)
            new_findings = db.get_findings_after(fix_ep.ended_at, pr_number=fix_ep.pr_number)
            net_new = [f for f in new_findings if f not in prior_findings]
            if net_new:
                findings.append(Finding(
                    detector_id="D10",
                    evidence={"fix_episode": fix_ep.id, "review_episode": rev_ep.id, "net_new_count": len(net_new)},
                    example_turns=[],
                    rc_mapping="RC-7",
                    severity="high",
                    remediation="CLAUDE.md"
                ))
    return findings
```

---

**D11 `scope_explosion`** → RC-6 proxy / proposal-D / C5
Severity: medium | Remediation: CLAUDE.md / new-skill

```python
INTENT_FILE_BASELINE = {
    "implement-feature": 8,
    "implement-bugfix": 5,
    "refactor": 10,
    "fix-findings": 4,
    "dev-lifecycle": 12,
    # others: use global median as fallback
}

def D11(episode_id: str, db: Store) -> Finding | None:
    episode = db.get_episode(episode_id)
    baseline = INTENT_FILE_BASELINE.get(episode.intent) or db.median_files_touched(episode.intent)
    if (episode.files_touched_count > baseline * 2
            and episode.outcome not in ("SUCCESS_CLEAN", "SUCCESS_PIVOT", "PENDING")):
        return Finding(
            detector_id="D11",
            evidence={
                "files_touched": episode.files_touched_count,
                "baseline": baseline,
                "ratio": round(episode.files_touched_count / baseline, 1)
            },
            example_turns=[],
            rc_mapping="RC-6",
            severity="medium",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D12 `generator_drift`** → RC-2
Severity: high | Remediation: CLAUDE.md / memory

```python
GENERATOR_PATTERNS = re.compile(r"gen-|.*-update\.(py|sh)|.*\.j2$|.*\.jinja2$")

def D12(episode_id: str, db: Store) -> Finding | None:
    edit_events = db.get_tool_events(episode_id, tools=("Edit", "Write"))
    violations = []
    for evt in edit_events:
        path = extract_path(evt.tool_args)
        if not path:
            continue
        dirname = os.path.dirname(path)
        generator_files = db.list_files_in_dir(dirname)
        has_generator = any(GENERATOR_PATTERNS.search(f) for f in generator_files)
        if has_generator:
            regen_found = any(
                e.tool_name == "Bash"
                and re.search(r"gen-|regen|make.*gen|python.*gen|uv run.*gen", e.tool_args or "")
                for e in db.get_events_after(episode_id, evt.id)
            )
            if not regen_found:
                violations.append((path, evt.id))
    if violations:
        return Finding(
            detector_id="D12",
            evidence={"files_without_regen": [v[0] for v in violations[:5]]},
            example_turns=[v[1] for v in violations[:3]],
            rc_mapping="RC-2",
            severity="high",
            remediation="CLAUDE.md"
        )
    return None
```

---

**D15 `automation_candidate`** → proposal-E / S4
Severity: info | Remediation: new-skill

```python
def D15(db: Store, min_cluster_size: int = 5, min_success_rate: float = 0.70) -> list[Pattern]:
    """
    Cluster episodes by (skill_sequence_signature, file_glob_pattern).
    Surface stable, high-success clusters as automation candidates.
    """
    episodes = db.get_all_episodes_with_metrics()
    clusters: dict[str, list[Episode]] = defaultdict(list)

    for ep in episodes:
        sig = compute_skill_sequence_sig(ep)
        glob = compute_file_glob(ep)
        key = f"{sig}::{glob}"
        clusters[key].append(ep)

    patterns = []
    for key, cluster_eps in clusters.items():
        if len(cluster_eps) < min_cluster_size:
            continue
        success_rate = sum(
            1 for e in cluster_eps
            if e.outcome in ("SUCCESS_CLEAN", "SUCCESS_PIVOT")
        ) / len(cluster_eps)
        if success_rate < min_success_rate:
            continue
        steps = extract_step_sequence(cluster_eps)
        stable = sequence_stability(steps) >= 0.8  # ≥80% of episodes share same step order
        if not stable:
            continue
        patterns.append(Pattern(
            skill_sequence_sig=key.split("::")[0],
            file_glob_pattern=key.split("::")[1],
            cluster_size=len(cluster_eps),
            success_rate=success_rate,
            step_sequence_stable=True,
            suggested_skill_name=suggest_skill_name(steps),
            suggested_steps=steps,
        ))
    return patterns
```

### Detectors deferred to v1.5

| ID | Name | Reason deferred |
|----|------|----------------|
| D13 | `fix_blast_radius` (RC-6) | Needs curated anti-pattern catalog first |
| D14 | `parallel_paths_drift` (RC-3) | Needs parallel-paths registry first |

### Detectors deferred to Phase 2 (LLM-required)

| ID | Name | RC/Proposal |
|----|------|------------|
| — | `silent_edits` | C3 |
| — | `reasoning_action_mismatch` | C7 |
| — | `sycophancy_upstream` | U4 |
| — | `instruction_decay` | C4 |
| — | `overcomplicated_solution` | C10 |

### RC coverage matrix

| RC | Description | Detectors |
|----|-------------|-----------|
| RC-1 | Same-agent author-and-tester | D2 (verification gap) |
| RC-2 | Generator/source pairs without enforced direction | D3, D7, D12 |
| RC-3 | Parallel paths drift | D14 (v1.5) |
| RC-4 | Bash as security-critical language | D7 (hallucinated symbol catches bash errors) |
| RC-5 | Review loop caps at 3 iters | D1, D9 |
| RC-6 | Finding scope = point not pattern (blast radius) | D11, D13 (v1.5) |
| RC-7 | Fix-pass introduces net-new defects | D2, D10 |

---

## CLI Grammar

```
insight [OPTIONS] COMMAND [ARGS]
```

### Commands

```
insight watch                              # continuous mode: all lanes (cocoindex Lane1+2 + NATS Lane3)

insight ingest
  --since DATE         ISO-8601 or relative (7d, 2w, 2025-03-24)
  --until DATE         default: now
  --projects LIST      comma-separated project names (default: all)
  --lane LANE          filter by lane: jsonl | git | nats | all (default: all)
  --dry-run            report what would be ingested, ¬write to DB
  --workers N          parallel sanitize workers (default: 4)

insight detect
  --episodes-only      run only episode-scoped detectors (skip D8, D10, D15 which are cross-episode)
  --detectors LIST     comma-separated (e.g. D1,D2,D7); default: all
  --rerun              clear existing findings for selected detectors, recompute
  --since DATE         limit to episodes started after DATE
  --until DATE         limit to episodes started before DATE

insight classify
  --llm-residue-only   skip rule-based classifier, run LLM only on PENDING with ambiguous signals
  --rerun              re-classify all non-PENDING episodes (use after new git/gh data)
  --since DATE

insight report
  --top N              cap findings per section (default: 10)
  --output PATH        file path; default stdout
  --format md|html|json  default: md
  --since DATE
  --until DATE
  --project NAME       filter to single project

insight compare WINDOW1 WINDOW2
  --metric METRIC      specific metric to compare (e.g. D1_rate, cost_outlier_pct)
  WINDOW1 / WINDOW2: "2025-03-24:2025-04-07" or "last-week" | "this-week" | "last-2w"

insight automation
  --min-cluster-size N   default: 5
  --min-success-rate R   float 0.0-1.0, default: 0.70
  --output PATH

insight calibrate
  --sample-size N        default: 50
  --save-labels FILE     JSON file to save bootstrap labels for spot-check
  --load-labels FILE     load previously saved labels (skip LLM bootstrap step)
  --llm-model MODEL      default: kimi (via litellm)

insight memory entity SLUG              # graph lookup for entity by slug
insight memory compiled SLUG            # show compiled truth (body_md) for entity
insight memory approve                  # list approval queue (status=pending); approve or reject
insight memory publish                  # approved items → actuate/pr.py → auto-PR

insight nats status                     # show Lane 3 subscriber status (connected | disconnected)
insight nats subscribe SUBJECT          # one-shot subscribe to NATS subject (debug)
insight nats replay --since DATE        # replay events from raw layer (lane='nats') for debugging

insight assemble
  --budget N           token budget for context window (default: 4000)
  --fresh-tail-days N  verbatim window for recent findings (default: 7)
  --goal SLUG          condition assembly on active goal (boosts matching entities)
  --format md|json     default: md
  Output: DAG-aware context block — fresh findings verbatim + older findings as compiled_truth
          summaries + bio-aware eviction (lowest-strength first when over budget)

insight goal
  push  --name TEXT [--issue N] [--project NAME] [--policy hybrid|error-prioritized|schema-fit-biased|recency-first]
  list
  complete [--outcome 0.0-1.0]   # propagates outcome score to entity strengths
  suspend
  resume
```

### Config file

`~/.claude/analysis/insight.toml`:

```toml
[paths]
raw_corpus     = "~/.claude/projects/"
sanitized_dir  = "~/.claude/analysis/sanitized/"
db_path        = "~/.claude/analysis/insight.db"

[sanitize]
trufflehog_bin = "~/.local/bin/trufflehog"
t2_redact      = true   # emails, IPs, MACs, paths

[segment]
idle_gap_enabled       = false
idle_gap_minutes       = 30
merge_window_minutes   = 120

[detect]
d5_cost_outlier_ratio  = 3.0
d6_ctx_token_threshold = 150000
d8_permission_threshold = 5
d15_min_cluster_size   = 5
d15_min_success_rate   = 0.70

[llm]
provider   = "fireworks"        # litellm provider key
model      = "accounts/fireworks/models/kimi-k2-5"
max_tokens = 1024
temperature = 0.1
enabled    = false              # Phase 2 only; must opt-in explicitly

[nats]
url            = "nats://localhost:4222"
creds_file     = "~/.config/lyra/nats.creds"
subscribe      = ["lyra.jobs.*", "lyra.results.*", "lyra.progress.*",
                  "lyra.llm.generate.*", "lyra.voice.*", "lyra.conversation.>"]

[graph]
decay_sigma_behavioral   = 30   # days — detectors, RCs, patterns
decay_sigma_world        = 90   # days — projects, persons, decisions
decay_sigma_instruction  = 60   # days — CLAUDE.md sections, skills

[compiled]
regen_threshold     = 0.1    # entity memory_strength change that triggers regen
approval_queue_path = "~/.claude/analysis/approval_queue/"

[actuation]
auto_pr             = false          # require explicit `insight memory publish`
target_branch_prefix = "insight/auto-"

[graph]
decay_basis              = "adaptive"  # clock | session | adaptive
decay_threshold          = 0.05        # prune entities with strength < this
half_life_behavioral     = 30          # days — detectors, RCs, patterns
half_life_world          = 90          # days — projects, persons, decisions
half_life_instruction    = 60          # days — CLAUDE.md sections, skills
schema_fit_fast_track    = 0.7         # above → consolidate fast (×1.5 half_life)
schema_fit_dark_matter   = 0.3         # below → dark matter bucket (×0.5 half_life)
conflict_overlap_threshold = 0.5       # Jaccard threshold for conflict detection
conflict_polarity_window = 40          # words to check for polarity signals

[assembly]
fresh_tail_days          = 7           # verbatim window (kind='raw', last N days)
budget_tokens            = 4000        # default context budget
eviction_policy          = "bio"       # bio (lowest-strength first) | fifo
dag_overflow_cap         = 0.3         # max fraction of budget for DAG overflow summaries
```

---

## Report Structure

### Sections

| # | Section | Content |
|---|---------|---------|
| 1 | Executive summary | period, episode count, top-3 detectors by frequency |
| 2 | Week-over-week improvements | detectors where rate decreased vs prior period |
| 3 | Regressions | detectors where rate increased |
| 4 | Effective patterns | intent classes with SUCCESS_CLEAN rate ≥ 80% |
| 5 | Ineffective patterns | intent classes with FAILED rate ≥ 20% |
| 6 | Automation candidates | D15 clusters (suggested skill name + step list) |
| 7 | Per-detector findings | ranked by score; ≤10 findings per detector |
| 8 | Calibration appendix | current P/R per detector; label counts |

### Per-finding block

```
### [D1] retry_loop — 23 episodes (RC-5)

Severity: high | Remediation: CLAUDE.md
Frequency rank: 1/13 | Score: 0.87

Examples:
  - session: a3f9b2c1 (lyra, implement-feature, 2025-03-28) — "same Bash cmd repeated 4× with identical stdout"
  - session: 8d1e5f02 (voiceCLI, fix-findings, 2025-04-01) — "Edit on same file 3× without Read between"
  - session: c7a2d3e9 (roxabi-forge, dev-lifecycle, 2025-04-05) — "trufflehog called 3× same path no new results"

Suggested action: Add "after N failed tool calls with same signature, stop and reframe" to CLAUDE.md
```

### Ranking formula

```
score(finding) = normalize(frequency) × severity_weight × actionability_weight

where:
  frequency        = episode_count for this detector in the report window
  severity_weight  = {"high": 1.0, "medium": 0.6, "low": 0.3}[finding.severity]
  actionability    = 1.0 if finding.remediation is not None else 0.5

  normalize(x)     = x / max_frequency_in_window   (0.0–1.0)
```

Per section: cap at top-10. Each finding: 3 anonymized session IDs + 1-line quote + remediation type.

### Calibration appendix format

```
## Calibration Appendix (as of 2025-04-07)

| Detector | Precision | Recall | Label count | Last calibrated |
|----------|-----------|--------|-------------|-----------------|
| D1       | 0.85      | 0.78   | 42          | 2025-04-01      |
| D2       | 0.91      | 0.65   | 38          | 2025-04-01      |
| …        |           |        |             |                 |

Note: P >= 0.7 AND R >= 0.5 = shipping threshold. Red = below threshold.
```

---

## Validation & Calibration Strategy

**Status: RECOMMENDED PENDING USER VALIDATION (Q12)**

### Bootstrap protocol

1. `insight calibrate --sample-size 50` draws stratified sample:
   - 10 episodes × 5 intent classes (dev-lifecycle, implement-feature, fix-findings, code-review, freeform)
   - Balanced across outcome classes (SUCCESS / PARTIAL / FAILED / PENDING)
2. For each sampled episode: run all detectors → collect `{episode_id, detector_id, fired: bool}`.
3. LLM bootstrap (Kimi via fireworks.ai): send de-noised episode summary + detector hypothesis → LLM returns `{detector_id, expected: bool, confidence: 0-1}`.
4. `--save-labels FILE`: save raw LLM labels for spot-check.
5. Human spot-check: only disagreements where `LLM.confidence > 0.7` AND `detector.fired != LLM.expected` → queue capped at 20 items.
6. P/R computed per detector; stored in `metrics` table.

### Shipping threshold

| Condition | Decision |
|-----------|---------|
| P >= 0.7 AND R >= 0.5 | Ship |
| P >= 0.7 AND R < 0.5 (high-leverage detector) | Ship with explicit justification note in calibration appendix |
| P < 0.7 | Hold; adjust detector, re-calibrate |

High-leverage = detector maps to RC with cross-project impact (RC-2, RC-5, RC-7 qualify).

### Re-calibration cadence

- Monthly for first 3 months.
- Quarterly thereafter.
- Trigger: detector fire rate changes > 20% week-over-week (automatic alert in report).

---

## Phasing

| Phase | Adds | LLM cost |
|---|---|---|
| 1 | Lane 1+2 ingest · D1-D15 · outcome classifier · behavioral report · memory kind envelope on findings | $0 |
| 1.5 | Lane 3 NATS adapter · buffer table · Layer 1 Raw extension · entities+relations tables · Retain Job · schema_fit computation · richer strength formula | $0 |
| 2 | LLM analyst (Kimi) · adaptive decay + nightly consolidation · Layer 3 Compiled Truth · DAG-aware `insight assemble` · goal stack (`insight goal`) · dark matter LLM mining (schema_fit<0.3 survivors) | ~$10-30/run |
| 3 | Layer 4 Actuation (approval queue + auto-PR) · conflict detection on queue · GEPA detector evolution · correction latency metric · outcome propagation (merge → fitness → entity strength) · longitudinal compare | ~$1-5/run |
| 4 | GEPA on CLAUDE.md sections · `lyra.memory.*` subjects live · multi-host corpus merge | TBD |

---

## Non-Goals

Explicit rejections (locked during grilling):

| Item | Reason rejected |
|------|----------------|
| Real-time enforcement / "LogForge" | Bait-and-switch; ¬address actual question |
| "Thinking Ratio" KPI | Goodhart-trivial; gameable by pasting boilerplate |
| Prescribing behavior changes | Surfaces patterns only; remediation is a separate phase |
| Multi-agent supervisor / orchestrator | Out of scope; roxabi-live's territory |
| v1: artifacts/ ingestion | Deferred to Phase 1.5 |
| v1: D13, D14 | Need curated catalogs first |
| Phase 2 detectors in Phase 1 | LLM-required; opt-in only |
| roxabi-vault | Deprecated — data not migrated |
| 2ndBrain | Deprecated — data not migrated |

---

## PR ↔ Episode Linkage

Stack of methods, first-match wins:

| Priority | Method | Source |
|----------|--------|--------|
| 1 | `episode.git_branch` matches `pr_state.head_ref` | gh PR list |
| 2 | Episode commit SHA present in PR commits | `git log` + gh PR commits |
| 3 | Issue number in branch name (e.g. `1036-fix-shell-injection`) → find PR for that issue | gh issue / PR cross-ref |
| 4 | Artifact file references | v1.5 |

---

## Repo Structure

**Status: LOCKED (architecture finalized 2026-05-05)**

```
roxabi-insight/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── .gitignore
├── .python-version                     # 3.13
├── src/
│   └── roxabi_insight/
│       ├── __init__.py
│       ├── cli.py                      # typer app — all commands (expanded)
│       ├── config.py                   # config.toml loader (all sections)
│       ├── ingest/
│       │   ├── jsonl.py                # (was tx_jsonl.py) Lane 1: parse JSONL → events stream
│       │   ├── git_github.py           # (was git_log.py + github.py) Lane 2: git log + gh API
│       │   ├── nats_adapter.py         # NEW: Lane 3 NATS subscriber (nats-py + roxabi-contracts)
│       │   └── sanitize.py             # trufflehog wrapper + regex + entropy
│       ├── raw/
│       │   └── store.py                # NEW: Layer 1 Raw DuckDB write/read
│       ├── segment/
│       │   ├── episode.py              # segmentation algorithm (JSONL lane only)
│       │   └── intent.py               # attributionSkill → intent taxonomy
│       ├── features.py                 # per-episode enrichment (JSONL lane only)
│       ├── detectors/
│       │   ├── tier_a.py               # D1-D8 (JSONL lane only)
│       │   ├── tier_b.py               # D9-D12 (JSONL lane only)
│       │   └── automation.py           # D15 (JSONL lane only)
│       ├── outcome.py                  # 8-state classifier + nightly re-classify (JSONL lane only)
│       ├── store.py                    # behavioral DuckDB read/write (eventually merge into raw/)
│       ├── graph/
│       │   ├── entities.py             # NEW: entity CRUD + decay
│       │   ├── relations.py            # NEW: relation CRUD + decay
│       │   └── resolution.py           # NEW: entity dedup (fuzzy + cosine)
│       ├── compiled/
│       │   ├── truth.py                # NEW: per-entity markdown compiler
│       │   └── impact.py               # NEW: impact analysis (which entities changed)
│       ├── actuate/
│       │   ├── queue.py                # NEW: approval queue
│       │   └── pr.py                   # NEW: auto-PR generator
│       ├── retain/
│       │   └── job.py                  # NEW: event-triggered entity extraction (heuristic, ¬LLM)
│       ├── assemble/
│       │   ├── context.py              # DAG-aware context window assembly (bio-aware eviction)
│       │   └── dag.py                  # DAG traversal: leaf→fact→summary→entity_profile levels
│       ├── goals/
│       │   └── stack.py                # Goal stack CRUD + retrieval policy conditioning
│       ├── strength/
│       │   └── formula.py              # strength(t) computation: decay × retrieval_boost × emotional_mult
│       ├── nightly/
│       │   └── consolidation.py        # NEW: nightly consolidation + decay recalc
│       ├── llm.py                      # litellm wrapper (Phase 2; no-op in Phase 1)
│       ├── report.py                   # ranking + md|html|json renderer
│       └── compare.py                  # window delta computation (Phase 3)
├── tests/
│   ├── test_segment.py
│   ├── test_detectors_tier_a.py
│   ├── test_detectors_tier_b.py
│   ├── test_outcome.py
│   ├── test_sanitize.py
│   └── fixtures/                       # minimal JSONL fixtures (¬real transcripts)
│       ├── session_basic.jsonl
│       ├── session_retry_loop.jsonl
│       ├── session_fix_no_verify.jsonl
│       └── session_generator_drift.jsonl
├── artifacts/
│   ├── specs/
│   ├── plans/
│   └── frames/
└── docs/
    ├── DATA-MODEL.md                   # DuckDB schema — authoritative
    ├── ARCHITECTURE.md
    └── DETECTORS.md                    # per-detector reference: signal, pseudocode, RC mapping
```

---

## Breadboard / Vertical Slices

### Slice V1 — Tracer bullet: 1 day → 1 episode in SQLite

**Goal:** end-to-end pipeline works for a single project's data. No detectors yet.
**Demo:** `insight ingest --since 1d --projects lyra` → `insight` shows 1+ rows in `episodes`.

| Affordance | Handler | Logic |
|------------|---------|-------|
| JSONL file reader | `tx_jsonl.py:parse_session` | read 1 `.jsonl`, emit raw events |
| Sanitize pass | `sanitize.py:sanitize_stream` | trufflehog + T1 regex only |
| De-noise pass | same stream | drop boilerplate types, truncate tool results |
| Episode segmenter | `episode.py:segment_episodes` | produce ≥1 Episode object |
| SQLite write | `store.py:upsert_episode` | write episodes + events tables |
| CLI entry | `cli.py:ingest` | wire everything |

AC:
- [ ] `insight ingest --since 1d --projects lyra` exits 0.
- [ ] `episodes` table has ≥1 row.
- [ ] `sanitization_log` has ≥0 rows (even if no redactions found).
- [ ] Re-running same command is idempotent (no duplicate rows).

---

### Slice V2 — Full sanitization + validation gates

**Goal:** T1+T2 redaction complete, trufflehog validation passes, determinism check passes.
**Demo:** `insight ingest --since 7d --dry-run` → reports redaction counts, 0 trufflehog findings on output.

AC:
- [ ] trufflehog re-scan of `~/.claude/analysis/sanitized/` returns 0 findings.
- [ ] 10-span spot-check script exits 0 (manual review helper).
- [ ] Re-run produces identical `sanitization_log` (determinism).
- [ ] T2 redaction: email/IP/MAC/home-path normalization working.

---

### Slice V3 — Tier A detectors (D1–D8) + findings table

**Goal:** all 8 Tier A detectors run against ingested episodes, findings stored.
**Demo:** `insight detect` → findings table populated; at least D2 fires on known test fixture.

AC:
- [ ] D1-D8 all execute without error on test fixtures.
- [ ] D2 fires on `session_fix_no_verify.jsonl` fixture (write without subsequent test call).
- [ ] D7 fires on `session_hallucinated_symbol.jsonl` fixture (ImportError in tool result).
- [ ] `findings` table populated with correct `rc_mapping` values.
- [ ] `insight detect --detectors D2` runs only D2.

---

### Slice V4 — Multi-source join + Tier B detectors (D9–D12)

**Goal:** git log + GitHub PR data ingested, Tier B detectors running.
**Demo:** `insight detect --detectors D9,D10,D12` on a lyra episode with known review loop → D9 fires.

AC:
- [ ] `git_events` table populated for at least 1 project.
- [ ] `pr_state` table populated via `gh` CLI for linked PRs.
- [ ] D9 fires for episode with `pr.review_iter_count >= 3 AND has_unresolved_blockers`.
- [ ] D12 fires on `session_generator_drift.jsonl` fixture.
- [ ] Episode-PR linkage: at least method 1 (branch match) working.

---

### Slice V5 — Outcome classifier + nightly re-classify

**Goal:** all episodes classified; PENDING resolved as signals arrive.
**Demo:** `insight classify` on lyra episodes from last 2 weeks → no PENDING for episodes > 12h old.

AC:
- [ ] `insight classify` exits 0.
- [ ] All episodes > 12h old have outcome ≠ PENDING.
- [ ] `insight classify --rerun` updates outcomes where new git/gh data changed signal.
- [ ] SUCCESS_CLEAN, PARTIAL_REVIEW_LOOPS, FAILED_LOOPS all appear in results (coverage test).

---

### Slice V6 — Report + compare

**Goal:** `insight report` produces readable, ranked output. `insight compare` computes deltas.
**Demo:** `insight report --since 7d --format md` → full report with calibration appendix section.

AC:
- [ ] Report has all 8 sections.
- [ ] Per-finding block shows ≤3 session IDs + 1-line quote.
- [ ] Score formula applied; detectors sorted by score descending.
- [ ] `insight compare last-week this-week` shows delta table.
- [ ] `--format json` output is valid JSON with `findings`, `patterns`, `calibration` keys.

---

### Slice V7 — D15 automation candidates + calibration

**Goal:** D15 cluster detection working; calibration loop bootstrapped.
**Demo:** `insight automation` on 6-week corpus → ≥1 cluster with suggested skill name.

AC:
- [ ] `insight automation` exits 0 on 6-week corpus.
- [ ] At least 1 pattern surfaced if corpus is large enough (may be 0 for small test window).
- [ ] `insight calibrate --sample-size 10 --save-labels /tmp/labels.json` exits 0 (even without LLM configured — falls back to heuristic labels).
- [ ] P/R values written to calibration appendix on next `insight report`.

---

## Open Questions

**Q13 — SQLite vs DuckDB** (**LOCKED: DuckDB** — see `docs/DATA-MODEL.md`)

**Q14 — CLI grammar** (RECOMMENDED PENDING VALIDATION)
Grammar above is a proposal. Validate with: does `insight ingest` + `insight detect` + `insight report` as separate commands match the expected workflow, or should `insight run` be a single-step shortcut?

**Q15 — Report ranking formula** (RECOMMENDED PENDING VALIDATION)
`frequency × severity_weight × actionability` is proposed. Validate: does this surface the right top findings vs a pure frequency sort?

**Q16 — Repo structure** (RECOMMENDED PENDING VALIDATION)
Structure above is proposed. Validate: is `detectors/tier_a.py` + `detectors/tier_b.py` split sufficient, or should each detector be its own file?

**[NEEDS CLARIFICATION: 1]** `attributionSkill` field presence rate in JSONL — confirmed as "present in JSONL schema" but actual field name and presence rate across 5,657 files needs verification during V1 ingest. If absent in older sessions, intent taxonomy falls back to branch-name heuristics + freeform.

**[NEEDS CLARIFICATION: 2]** Permission prompt event type — D8 relies on `event_type = 'permission_prompt'`. Actual event type name in Claude Code JSONL schema needs verification during V1 ingest.

**[NEEDS CLARIFICATION: 3]** Episode token estimate source — Claude Code JSONL may or may not include `usage` fields per turn. Token estimation may need to fall back to character-count heuristic (1 token ≈ 4 chars) if `usage` is absent.

**Q17 — `lyra.conversation.*` NATS domain** (OPEN)
Needs new ADR in lyra before Lane 3 can ingest user turns. `ConversationTurnEvent` schema and subject literal (`lyra.conversation.>`) not yet in `roxabi-contracts`. Lane 3 subscriber will skip this subject family until ADR is merged.

**Q18 — `lyra.memory.*` NATS domain** (OPEN)
Needs new ADR in lyra before insight can publish findings to the bus. Required subjects: `lyra.memory.*` with `MemoryInsightEvent`, `MemoryQueryRequest/Response`, `MemoryReinforceEvent`. Blocked until Phase 4.

**Q19 — Entity resolution threshold** (OPEN)
Cosine similarity > 0.85 proposed for auto-merge (consistent with lyra memory design). Needs validation against real corpus before enabling. Below threshold: entities remain separate; manual merge via `insight memory approve`.

**Q20 — Adaptive decay calibration** (OPEN)
`decay_basis=adaptive` requires `avg_session_interval_days` per project, derived from the JSONL corpus on first ingest. Projects with < 7 sessions default to `clock` basis until sufficient history exists.

**Q21 — Schema fit threshold validation** (OPEN)
`schema_fit_fast_track=0.7` and `schema_fit_dark_matter=0.3` are proposed from hippo defaults. Validate against the 6-week corpus: does `schema_fit < 0.3` correctly route unknown-RC findings to the dark matter bucket?

---

## Constraints

- Python 3.13 (`.python-version` pinned).
- `uv` for package management; `hatchling` build backend.
- No Anthropic models as judges (same-model bias). Phase 2: Kimi/GLM via fireworks.ai.
- `trufflehog --no-verification` (never `--verification`).
- No live API calls during sanitization.
- DuckDB at `~/.claude/analysis/insight.duckdb` — single-file, portable, no server (locked, Q13).
- `nats-py >= 2.7` for Lane 3 subscriber.
- `roxabi-contracts` from lyra monorepo via uv GitHub source (typed NATS envelopes + subject literals).
- CLI must work on M₁ (Ubuntu Server 24.04+) and M₂ (Pop!_OS, dev).
- File length limit: 300 lines/file (per quality gate in stack.yml). Detectors split into tier_a.py / tier_b.py / automation.py to respect this.

---

## Success Criteria

### Phase 1 complete

- [ ] `insight ingest --since 6w` ingests all 5,657 files without crash.
- [ ] Sanitization: 0 trufflehog findings on sanitized corpus.
- [ ] Episode count > 0 per project.
- [ ] All 13 detectors (D1-D12, D15) execute without error.
- [ ] `insight report --format md` produces all 8 sections.
- [ ] RC-mapping coverage: RC-1, RC-2, RC-5, RC-6, RC-7 each have ≥1 firing detector.
- [ ] `insight compare last-2w this-2w` works (even if delta is 0).
- [ ] Idempotent: re-run `ingest` + `detect` → same results.
- [ ] No PII leak: spot-check 10 random events → 0 T1 leaks.
- [ ] Total runtime for full 1.5 GB corpus: < 30 minutes on M₁.

### Calibration baseline

- [ ] `insight calibrate --sample-size 50` completes.
- [ ] D1, D2, D7 achieve P >= 0.7 AND R >= 0.5 (highest-confidence detectors).
- [ ] Calibration appendix appears in every report.

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Analytics substrate | DuckDB (LOCKED) | Columnar analytics, native Parquet, cross-source joins; see DATA-MODEL.md |
| DataFrame lib | polars | Faster than pandas for streaming parse of large JSONL corpus |
| LLM provider | fireworks.ai (Kimi K2.5) | Non-Anthropic = eliminates same-model bias; cost ~$10-30/full run |
| Sanitization | trufflehog + regex + entropy | Defense-in-depth; trufflehog catches structured secrets, regex catches domain-specific tokens, entropy catches high-randomness residue |
| Episode unit | logical task boundary | Session is too granular (dev-core:dev opens fresh sessions per phase); conversation is too coarse |
| Detectors | heuristic-first | LLM-as-judge = "like asking a cat to do accounting"; heuristics cover 80%+ at $0 cost |
| Intent classification | attributionSkill-first | 19/20 intents auto-classify from field; only freeform needs LLM (Phase 2) |
| 3-lane ingest | JSONL + git/gh + NATS | Covers behavioral + outcome + conversational signals in one store |
| Memory layer | lyra-memory 4-layer design | Raw → Graph → Compiled Truth → Actuation; insight absorbs lyra design (one project, not two) |
| Incremental engine | cocoindex | Delta-only, `(input_hash ⊕ code_hash)` memoization, free watch mode |
| NATS contracts | roxabi-contracts | Typed Pydantic envelopes, subject literals, ADR-049 trust model |
| Memory strength model | hippo-memory formula | reward_factor + retrieval_boost + emotional_multiplier closes the remediation feedback loop |
| Decay basis | adaptive (default) | Intermittent project use auto-extends half_life; no per-project config |
| Schema fit | IDF-weighted Jaccard (no LLM) | Routes findings to known-RC vs dark-matter at $0; LLM only sees survivors |
| Kind envelope | raw\|distilled\|superseded\|archived | Append-only on raw; full audit trail; GDPR-correct archive path |
| Context assembly | DAG-aware bio-eviction | Lowest-strength evicted first; high-importance old findings survive over low-strength recent ones |
| Goal stack | dlPFC model (/dev #N = active goal) | Active issue conditions recall; outcome propagates back to entity strength on complete |
| Actuation | approval_queue + auto-PR | Human gate before any CLAUDE.md/skill/memory diff lands |
