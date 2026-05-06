---
title: Data Model — historique (LOCKED 2026-05-05 · partial-superseded 2026-05-06)
status: superseded-partial
superseded_by: docs/adr/ADR-003, ADR-005, ADR-011 — DATA-MODEL à scinder
date: 2026-05-05
---

# Data Model — Storage, Schema, Migrations

Status: **LOCKED** (Q13 grilling, 2026-05-05). Covers behavioral schema (Lane 1+2) and memory layer tables (Layers 1–4). Supersedes the `RECOMMENDED PENDING` block in `artifacts/specs/spec-roxabi-insight.md` for Q13.

> **⚠ SUPERSEDED PARTIELLEMENT (2026-05-06)** — Suite à la révision architecturale (ADR-001..011) :
>
> - Le **schéma `events`** ci-dessous est JSONL-centric (`tool_name`, `tool_args_hash`, `error_flag`, `correction_flag`). À **généraliser** côté cortex-insight pour accueillir mails / telegram / NATS Lyra (les colonnes JSONL-spécifiques migrent dans `payload JSON`). Cf. ADR-003.
> - Les **tables Layer 2** (`entities`, `relations`, `compiled_truth`, `approval_queue`, `buffer`, `goal_stack`) déménagent côté **cortex-memory**. Cf. ADR-003, ADR-005.
> - Le **Retain Job** (extraction d'entités) déménage côté memory · le contrat publish entre les services est désormais **`Observation`** typée, pas `EntityProposal`. Cf. ADR-005.
> - Le **storage** reste DuckDB v1 mais avec triggers de revisit pour memory → KuzuDB. Cf. ADR-011.
> - La **taxonomie d'entités** (`type`, `subtype`) est en cours de refonte biomimétique. Cf. ADR-009 (DEFERRED).
>
> **À ce stade :**
> - Vue d'ensemble : `docs/ARCHITECTURE.md`
> - Décisions : `docs/adr/`
> - Ce DATA-MODEL.md sera scindé en `docs/insight/DATA-MODEL.md` (raw + behavioral) et `docs/memory/DATA-MODEL.md` (graphe générique post-ADR-009)
> - Encore valide à ce stade : tables `episodes`, `metrics`, `findings`, `pr_state`, `git_events`, `issue_events`, `sanitization_log` (vont dans insight) · cardinality estimates · indexes (à reproduire dans les nouveaux schémas)
> - **Obsolète** : structure unifiée d'un seul DuckDB · colonnes JSONL-centric dans `events` générique · présence des tables Layer 2 dans le même DB que les events

Let:
  Σ := canonical store | ε := events table | φ := findings table | κ := calibration tables

---

## 1. Storage engine

**DuckDB** — single file at `~/.claude/analysis/insight.duckdb`.

| Reason | Detail |
|---|---|
| Workload is analytics | aggregate-by intent×detector×outcome×week dominates queries |
| Native Parquet | stages 2 (de-noised events) and 4 (features) export to `.parquet` for cheap re-runs |
| Cross-source joins | Tx + git + GitHub fusion is columnar-friendly |
| Concurrency profile | v1 ingest is one-shot batch; reports are read-only — no contention |
| Sharing | DuckDB can attach SQLite if export-to-SQLite is needed |

Out: SQLite (slower aggregates, no native Parquet).

---

## 2. Tables

### 2.1 `episodes`

```sql
CREATE TABLE episodes (
    id                    VARCHAR PRIMARY KEY,           -- ulid
    project               VARCHAR NOT NULL,              -- e.g., "lyra", "imageCLI"
    intent                VARCHAR NOT NULL,              -- one of 20 intent classes
    started_at            BIGINT NOT NULL,               -- epoch ms
    ended_at              BIGINT NOT NULL,
    branch                VARCHAR,
    cwd                   VARCHAR,
    orchestrator_skill    VARCHAR,                       -- NULL if no active orchestrator
    outcome               VARCHAR,                       -- 8-state enum or PENDING
    outcome_classified_at BIGINT,
    pr_number             INTEGER,
    issue_number          INTEGER,
    files_touched_count   INTEGER DEFAULT 0,
    token_estimate        BIGINT DEFAULT 0,
    user_correction_count INTEGER DEFAULT 0,
    sub_agent_count       INTEGER DEFAULT 0,
    trace_outcome         VARCHAR                        -- mirrors outcome; Layer.Trace compat (success|failure|partial|null)
);
```

### 2.2 `events`

One row per JSONL entry. Single denormalized table (no `tool_calls` split).

```sql
CREATE TABLE events (
    id                BIGINT PRIMARY KEY,
    episode_id        VARCHAR REFERENCES episodes(id),
    session_id        VARCHAR,                          -- source JSONL session uuid
    parent_uuid       VARCHAR,                          -- conversation chain
    timestamp         BIGINT NOT NULL,
    type              VARCHAR NOT NULL,                 -- user | assistant | tool_use | tool_result | system
    tool_name         VARCHAR,                          -- NULL for non-tool events
    tool_args_hash    VARCHAR,                          -- D1 retry_loop signature match
    exit_code         INTEGER,                          -- bash exit; NULL otherwise
    error_flag        BOOLEAN DEFAULT FALSE,            -- precomputed; D7 input
    correction_flag   BOOLEAN DEFAULT FALSE,            -- precomputed; D4 input
    payload_json      JSON,                             -- sanitized + truncated body
    raw_offset        BIGINT,                           -- byte offset into source jsonl
    raw_file          VARCHAR,                          -- relative path to source file
    lane              VARCHAR DEFAULT 'jsonl',          -- 'jsonl' | 'git' | 'nats'
    nats_subject      VARCHAR,                          -- populated for lane='nats'
    trace_id          VARCHAR,                          -- ContractEnvelope.trace_id (for lane='nats')
    in_buffer             BOOLEAN DEFAULT FALSE,         -- TRUE while awaiting Retain Job processing
    owner                 VARCHAR                        -- 'agent:claude-code' | 'agent:lyra'
);
```

**Key choice:** `error_flag` and `correction_flag` precomputed at ingest. Detectors run as cheap SQL aggregates instead of re-scanning text.

### 2.3 `metrics`

```sql
CREATE TABLE metrics (
    episode_id         VARCHAR PRIMARY KEY REFERENCES episodes(id),
    tool_count         INTEGER DEFAULT 0,
    edit_count         INTEGER DEFAULT 0,
    test_count         INTEGER DEFAULT 0,
    failure_count      INTEGER DEFAULT 0,
    retry_count        INTEGER DEFAULT 0,
    review_iter_count  INTEGER DEFAULT 0,
    duration_ms        BIGINT
);
```

### 2.4 `detection_runs` + `findings`

Findings versioned by `run_id`. Old runs retained for trend analysis.

```sql
CREATE TABLE detection_runs (
    id                    VARCHAR PRIMARY KEY,           -- ulid
    started_at            BIGINT NOT NULL,
    completed_at          BIGINT,
    detector_set          VARCHAR,                       -- "v1", "v1.1"
    sanitization_version  VARCHAR,
    config_json           JSON
);

CREATE TABLE findings (
    id                BIGINT PRIMARY KEY,
    run_id            VARCHAR REFERENCES detection_runs(id),
    episode_id        VARCHAR REFERENCES episodes(id),
    detector_id       VARCHAR NOT NULL,                 -- D1..D15
    confidence        DOUBLE,                            -- 0.0..1.0
    severity          VARCHAR,                           -- low | medium | high
    event_id_start    BIGINT,                            -- span anchor
    event_id_end      BIGINT,
    evidence_text     TEXT,                              -- short quote, sanitized
    remediation_type  VARCHAR,                           -- claude_md_edit | new_skill | memory_entry | settings_allowlist | none
    created_at        BIGINT NOT NULL,
    kind                  VARCHAR DEFAULT 'raw',         -- raw | distilled | superseded | archived
    owner                 VARCHAR                        -- 'agent:claude-code' | 'agent:lyra'
);
-- kind invariant: 'raw' rows are append-only (never directly deleted). Archive via suppress=TRUE which flips kind to 'archived'.
```

### 2.5 `patterns` (Phase 2 / clustering)

```sql
CREATE TABLE patterns (
    id                  BIGINT PRIMARY KEY,
    name                VARCHAR,                         -- LLM-named in Phase 2
    detector_id         VARCHAR,
    episode_count       INTEGER,
    success_count       INTEGER,                         -- pattern_success_rate = success_count / episode_count
    sample_episode_ids  JSON                             -- array
);
```

### 2.6 Multi-source ingest tables

```sql
CREATE TABLE pr_state (
    pr_number          INTEGER,
    repo               VARCHAR,
    head_branch        VARCHAR,
    state              VARCHAR,                          -- open | closed | merged
    ci_status          VARCHAR,
    review_iter_count  INTEGER,
    merged_at          BIGINT,
    fetched_at         BIGINT,
    PRIMARY KEY (repo, pr_number)
);

CREATE TABLE git_events (
    id              BIGINT PRIMARY KEY,
    sha             VARCHAR,
    repo            VARCHAR,
    branch          VARCHAR,
    timestamp       BIGINT,
    is_revert       BOOLEAN,
    files_touched   JSON                                 -- array
);

CREATE TABLE issue_events (
    id            BIGINT PRIMARY KEY,
    issue_number  INTEGER,
    repo          VARCHAR,
    label         VARCHAR,
    severity      VARCHAR,                               -- e.g., severity:prod, incident
    occurred_at   BIGINT
);
```

### 2.7 Audit + sanitization

```sql
CREATE TABLE sanitization_log (
    id                          BIGINT PRIMARY KEY,
    raw_file                    VARCHAR,
    redaction_count_by_type     JSON,                    -- {"github_pat": 0, "home_path": 381, ...}
    truncation_bytes_saved      BIGINT,
    boilerplate_dedups          INTEGER,
    sanitized_at                BIGINT
);

CREATE TABLE _schema_migrations (
    version       VARCHAR PRIMARY KEY,                   -- "0001", "0002", ...
    applied_at    BIGINT NOT NULL,
    description   TEXT
);
```

### 2.8 Calibration tables (per Q12)

```sql
CREATE TABLE calibration_runs (
    id                  VARCHAR PRIMARY KEY,
    version             VARCHAR NOT NULL,                -- "v1.0"
    started_at          BIGINT NOT NULL,
    completed_at        BIGINT,
    sample_size         INTEGER NOT NULL,
    sample_episode_ids  JSON,                            -- frozen sample list per Q12b
    labeling_method     VARCHAR,                         -- "kimi_bootstrap_human_correct"
    status              VARCHAR                          -- pending | in_review | complete
);

CREATE TABLE calibration_labels (
    id              BIGINT PRIMARY KEY,
    cal_run_id      VARCHAR REFERENCES calibration_runs(id),
    episode_id      VARCHAR REFERENCES episodes(id),
    detector_id     VARCHAR NOT NULL,
    true_positive   BOOLEAN NOT NULL,                    -- ground truth from human verdict
    detector_fired  BOOLEAN NOT NULL,                    -- what the detector said
    label_source    VARCHAR,                             -- kimi_bootstrap | human_corrected
    notes           TEXT
);

CREATE TABLE calibration_metrics (
    cal_run_id        VARCHAR REFERENCES calibration_runs(id),
    detector_id       VARCHAR NOT NULL,
    precision         DOUBLE,
    recall            DOUBLE,
    f1                DOUBLE,
    n_pos             INTEGER,
    n_neg             INTEGER,
    threshold_p_min   DOUBLE,                            -- per Q12d tiered thresholds
    threshold_r_min   DOUBLE,
    passed            BOOLEAN,
    PRIMARY KEY (cal_run_id, detector_id)
);
```

### 2.9 Memory Layer tables

Layer 2 (Knowledge Graph), Layer 3 (Compiled Truth), Layer 4 (Actuation).

```sql
-- Layer 2: Knowledge Graph

CREATE TABLE entities (
    id                  VARCHAR PRIMARY KEY,    -- ulid
    slug                VARCHAR UNIQUE NOT NULL, -- "rc:RC-2" · "project:lyra" · "detector:D7"
    type                VARCHAR NOT NULL,       -- behavioral | world | instruction | nats
    subtype             VARCHAR,                -- detector|rc|pattern|episode|project|person|job|turn|skill|claude_md|...
    name                VARCHAR,
    -- Strength fields (hippo-memory model)
    memory_strength     DOUBLE DEFAULT 1.0,    -- current computed strength (0..1)
    half_life_days      DOUBLE DEFAULT 30.0,   -- base half-life; modulated by reward_factor
    retrieval_count     INTEGER DEFAULT 0,     -- boost: 1 + 0.1*log2(retrieval_count+1)
    last_reinforced     BIGINT,                -- epoch ms of last retrieval
    outcome_positive    INTEGER DEFAULT 0,     -- cumulative positive outcome count
    outcome_negative    INTEGER DEFAULT 0,     -- cumulative negative outcome count
    emotional_valence   VARCHAR DEFAULT 'neutral', -- neutral(1.0)|positive(1.3)|negative(1.5)|critical(2.0)
    schema_fit          DOUBLE DEFAULT 0.5,    -- 0..1: fit to existing patterns; <0.3=dark matter; >0.7=fast-track
    pinned              BOOLEAN DEFAULT FALSE,  -- TRUE = infinite strength, no decay
    conflicts_with      JSON,                  -- array of entity slugs with detected contradictions
    created_at          BIGINT NOT NULL,
    updated_at          BIGINT NOT NULL
);

-- Strength formula (hippo-memory model):
-- strength(t) = base_strength
--               × (0.5 ^ (Δt / effective_half_life))
--               × retrieval_boost
--               × emotional_multiplier
--
-- where:
--   reward_factor       = 1 + 0.5 × ((outcome_positive - outcome_negative) / (outcome_positive + outcome_negative + 1))
--   effective_half_life = half_life_days × reward_factor          -- range: half_life×0.5 .. half_life×1.5
--   retrieval_boost     = 1 + (0.1 × log₂(retrieval_count + 1))
--   emotional_multiplier = neutral:1.0 | positive:1.3 | negative:1.5 | critical:2.0
--
-- Severity → emotional_valence mapping: high=critical | medium=negative | low=neutral
-- Schema fit → half_life modifier: schema_fit>0.7 → ×1.5 | schema_fit<0.3 → ×0.5

CREATE TABLE relations (
    id              VARCHAR PRIMARY KEY,    -- ulid
    source_id       VARCHAR NOT NULL REFERENCES entities(id),
    target_id       VARCHAR NOT NULL REFERENCES entities(id),
    type            VARCHAR NOT NULL,       -- fires_in|maps_to|co_occurs|remediated_by|supersedes|triggered_by|costs|decided_in|reinforces
    weight_temporal DOUBLE DEFAULT 1.0,    -- exp(-Δt/σ); σ per type in config [graph]
    weight_semantic DOUBLE DEFAULT 1.0,
    confidence      DOUBLE DEFAULT 0.9,
    last_observed   BIGINT NOT NULL,
    metadata_json   JSON
);

-- Layer 3: Compiled Truth

CREATE TABLE compiled_truth (
    id              VARCHAR PRIMARY KEY,    -- ulid
    entity_id       VARCHAR NOT NULL REFERENCES entities(id),
    version         INTEGER NOT NULL,
    body_md         TEXT NOT NULL,          -- per-entity markdown (RC-2.md body, etc.)
    source_run_ids  JSON,                   -- detection_runs that drove this version
    generated_at    BIGINT NOT NULL,
    superseded_by   VARCHAR,                -- FK to next compiled_truth.id
    kind                VARCHAR DEFAULT 'distilled'   -- distilled | superseded | archived
);

-- Layer 4: Actuation

CREATE TABLE approval_queue (
    id           VARCHAR PRIMARY KEY,       -- ulid
    entity_id    VARCHAR REFERENCES entities(id),
    diff_type    VARCHAR NOT NULL,          -- claude_md | memory_entry | skill | allowlist
    diff_body    TEXT NOT NULL,             -- actual diff, ready to apply
    target_path  VARCHAR NOT NULL,          -- e.g. ~/projects/lyra/CLAUDE.md
    status       VARCHAR DEFAULT 'pending', -- pending | approved | rejected
    created_at   BIGINT NOT NULL,
    decided_at   BIGINT
);

-- Buffer: working memory for in-flight events (primarily Lane 3 NATS)
-- Events land here before the Retain Job processes them into the graph.
-- Prevents noise from contaminating entity decay calculations.
CREATE TABLE buffer (
    id           VARCHAR PRIMARY KEY,   -- ulid
    lane         VARCHAR NOT NULL,      -- 'nats' primarily; occasionally 'jsonl' for streaming
    nats_subject VARCHAR,
    trace_id     VARCHAR,
    payload_json JSON,
    arrived_at   BIGINT NOT NULL,
    processed    BOOLEAN DEFAULT FALSE  -- TRUE after Retain Job promotes to events + entities
);

-- Goal stack: /dev #N as active goal (dlPFC model)
-- Active goal conditions recall: boosts entities tagged with matching issue/project.
CREATE TABLE goal_stack (
    id               VARCHAR PRIMARY KEY,   -- ulid
    session_id       VARCHAR,
    goal_name        VARCHAR NOT NULL,      -- e.g. "issue:1234" | "lyra auth refactor"
    issue_number     INTEGER,
    project          VARCHAR,
    status           VARCHAR DEFAULT 'active',   -- active | suspended | completed
    retrieval_policy VARCHAR DEFAULT 'hybrid',   -- error-prioritized | schema-fit-biased | recency-first | hybrid
    outcome_score    DOUBLE,               -- set on complete; propagates to entity strength
    created_at       BIGINT NOT NULL,
    completed_at     BIGINT
);
```

---

## 3. Indexes

```sql
-- episodes
CREATE INDEX episodes_project_intent_outcome ON episodes(project, intent, outcome);
CREATE INDEX episodes_window               ON episodes(started_at, ended_at);
CREATE INDEX episodes_pr                   ON episodes(pr_number) WHERE pr_number IS NOT NULL;
CREATE INDEX episodes_branch               ON episodes(branch);

-- events
CREATE INDEX events_episode_idx            ON events(episode_id);
CREATE INDEX events_ts_idx                 ON events(timestamp);
CREATE INDEX events_tool_idx               ON events(tool_name) WHERE tool_name IS NOT NULL;
CREATE INDEX events_error_idx              ON events(error_flag) WHERE error_flag = TRUE;

-- findings
CREATE INDEX findings_run_idx              ON findings(run_id);
CREATE INDEX findings_episode_idx          ON findings(episode_id);
CREATE INDEX findings_detector_idx         ON findings(detector_id);

-- multi-source
CREATE UNIQUE INDEX pr_state_repo_num      ON pr_state(repo, pr_number);
CREATE INDEX git_events_repo_ts            ON git_events(repo, timestamp);
CREATE INDEX git_events_branch             ON git_events(branch);
CREATE INDEX git_events_revert             ON git_events(is_revert) WHERE is_revert = TRUE;
CREATE INDEX issue_events_repo_num         ON issue_events(repo, issue_number);
CREATE INDEX issue_events_severity         ON issue_events(severity) WHERE severity IS NOT NULL;

-- entities
CREATE UNIQUE INDEX entities_slug         ON entities(slug);
CREATE INDEX entities_type_subtype        ON entities(type, subtype);
CREATE INDEX entities_memory_strength     ON entities(memory_strength);

-- relations
CREATE INDEX relations_source             ON relations(source_id);
CREATE INDEX relations_target             ON relations(target_id);
CREATE INDEX relations_type               ON relations(type);
CREATE INDEX relations_weight_temporal    ON relations(weight_temporal);

-- compiled_truth
CREATE INDEX compiled_truth_entity        ON compiled_truth(entity_id);
CREATE INDEX compiled_truth_version       ON compiled_truth(entity_id, version DESC);

-- approval_queue
CREATE INDEX approval_queue_status        ON approval_queue(status) WHERE status = 'pending';
CREATE INDEX approval_queue_entity        ON approval_queue(entity_id);

-- buffer
CREATE INDEX buffer_processed ON buffer(processed) WHERE processed = FALSE;
CREATE INDEX buffer_arrived   ON buffer(arrived_at);

-- goal_stack
CREATE INDEX goal_stack_status  ON goal_stack(status) WHERE status = 'active';
CREATE INDEX goal_stack_issue   ON goal_stack(issue_number) WHERE issue_number IS NOT NULL;

-- entities (new columns)
CREATE INDEX entities_schema_fit        ON entities(schema_fit);
CREATE INDEX entities_emotional_valence ON entities(emotional_valence);
CREATE INDEX entities_pinned            ON entities(pinned) WHERE pinned = TRUE;
```

---

## 4. Migrations

| Param | Value |
|---|---|
| Approach | File-based SQL — `src/roxabi_insight/migrations/0001_initial.sql`, `0002_*.sql`, ... |
| Tracker | `_schema_migrations` table (version, applied_at, description) |
| Direction | Forward-only |
| Failure mode | Schema mismatch detected → **regenerate** the entire DB from raw JSONL (deterministic pipeline) rather than patch — acceptable for v1 because all data is regenerable |
| Out | Alembic (overkill); `sqlite-utils.migrate` (locks us to SQLite) |

---

## 5. Quick reference — table cardinality estimates

| Table | Row count estimate (6 weeks, all projects) |
|---|---|
| `episodes` | ~2,000 — 5,000 |
| `events` | ~500,000 — 2,000,000 |
| `metrics` | 1:1 with episodes |
| `detection_runs` | tens (one per re-run) |
| `findings` | ~10,000 — 50,000 across all runs |
| `pr_state` | ~200 (PRs touched in window) |
| `git_events` | ~5,000 (commits + reverts) |
| `issue_events` | ~500 |
| `calibration_*` | ~50 episodes × 13 detectors = ~650 labels per cycle |
| `entities` | ~500–2,000 (behavioral + world + instruction) |
| `relations` | ~5,000–20,000 |
| `compiled_truth` | ~500–2,000 (1+ versions per entity) |
| `approval_queue` | tens–hundreds (consumed as approved) |
| `buffer` | tens–hundreds (short-lived; cleared after Retain Job) |
| `goal_stack` | one per active session (few at any time) |

---

## 6. Open dependencies

| Resolves in | Item |
|---|---|
| Q14 | CLI grammar invocations against this schema |
| Q15 | Report templates query this schema |
| Q16 | Repo layout — `src/roxabi_insight/store.py` is the DuckDB wrapper |
| Empirical | `attributionSkill` field presence rate (drives intent column population) |
| Empirical | `usage` field for token estimate (drives `token_estimate` column source) |
| Q17 | `lyra.conversation.*` NATS domain — new ADR in lyra required before Lane 3 ingests user turns |
| Q18 | `lyra.memory.*` NATS domain — new ADR in lyra required before insight publishes findings to bus |
| Empirical | NATS event volume on M₁ hub — drives `lane='nats'` cardinality for events table |
| Q20 | Adaptive decay calibration — `decay_basis=adaptive` requires measuring `avg_session_interval_days` per project from the JSONL corpus before first sleep cycle |
