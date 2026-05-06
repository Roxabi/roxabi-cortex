---
title: spec-cortex-insight
status: draft
date: 2026-05-06
related_adrs: [ADR-001, ADR-002, ADR-003, ADR-004, ADR-005, ADR-006, ADR-007, ADR-008, ADR-011]
related_specs: [spec-cortex-memory]
superseded_by: -
---

## Context

**cortex-insight** est le service `lake + ETL` de l'écosystème **roxabi-cortex** (ADR-001).

Architecture d'ensemble : `docs/ARCHITECTURE.md`. Décisions structurantes :

| ADR | Sujet | Impact direct sur insight |
|---|---|---|
| ADR-003 | Lake/warehouse split | insight = lake · ne stocke pas le graphe · ne doit pas connaître l'état de memory |
| ADR-004 | Producteurs → insight uniquement | point d'entrée unique du brut multi-source |
| ADR-005 | Contrat `Observation` | insight encode, publie ; memory consolide · frontière nette |
| ADR-006 | `roxabi-contracts` extension | `insight.py` = `RawEventEnvelope` + subjects publish |
| ADR-007 | Mode d'arrivée (push/pull/hook) | open — décidé par source à l'implémentation |
| ADR-008 | Monorepo workspace | `packages/insight/` dans `roxabi-cortex/` |
| ADR-011 | DuckDB v1 | `~/.cortex/insight.duckdb` · OLAP append-heavy |
| ADR-002 | Podman + Quadlet | `ghcr.io/roxabi/cortex-insight:staging` · `roxabi.network` |

Frontière avec memory : insight produit des `Observation` typées (cf. ADR-005) publiées sur
`roxabi.memory.observations.publish`. Il n'écrit jamais dans `memory.duckdb`.

---

## Goal

Ingérer tout le brut multi-source, le sanitizer, l'encoder, et produire :

1. Un raw event log (append-only, lane-tagged) dans `insight.duckdb`.
2. Des épisodes segmentés + findings issus des détecteurs D1-D15 (pipeline behavioral).
3. Des `Observation` typées publiées à cortex-memory (une par finding).
4. Des rapports et comparaisons longitudinales à la demande.

---

## Pipeline behavioral (Lane JSONL)

Ce pipeline s'applique à la lane `jsonl` (Claude Code transcripts). Les autres lanes (mail, Telegram, NATS) ont leurs propres pipelines `relationship/`, `voice/`, etc. à définir.

```
[1]           [2]          [3]          [4]         [5]         [6]           [7]         [8]
raw JSONL  →  sanitize  →  de-noise  →  segment  →  features  →  detect  →  DuckDB  →  encode+publish
               + regex        + trunc     (episode)   + enrich      D1-D15      ↑           Observation
                                                          ↑                  calibration     → NATS
               ↓                                         |                    loop
         multi-source join: git log + gh PR/CI/issues ──┘
```

Notes :
- Stages 1-3 = streaming pass unique par fichier (pas de second read du brut).
- Stage 4 = stateful ; consomme le stream de-noised.
- Stage 5 = enrichissement par épisode depuis DuckDB + git/gh side-channels.
- Stage 6 = lectures pures contre tables `episodes` + `events`.
- LLM analyst (Phase 2 uniquement) = couche optionnelle entre detect et report.
- Calibration loop : feed-back vers les seuils des détecteurs (stocké dans `calibration_metrics`).

---

## Sanitization Pass

S'exécute en streaming (stage 2). Pas de second read du brut.

### Outil

`trufflehog filesystem <path> --no-verification --json` sur `~/.claude/projects/`.
Binaire : `~/.local/bin/trufflehog`.
`--no-verification` obligatoire — le mode vérification tente les tokens contre des APIs live.

### Tiers de redaction

| Tier | Type | Traitement | Tag |
|------|------|-----------|-----|
| T1 (must) | API keys (OpenAI, Anthropic, AWS, GCP) | Redact | `<REDACTED:API_KEY>` |
| T1 (must) | JWTs | Redact | `<REDACTED:JWT>` |
| T1 (must) | Bearer tokens | Redact | `<REDACTED:BEARER>` |
| T1 (must) | Telegram bot tokens | Redact | `<REDACTED:BOT_TOKEN>` |
| T1 (must) | Discord tokens | Redact | `<REDACTED:DISCORD_TOKEN>` |
| T1 (must) | NATS NKEYs | Redact | `<REDACTED:NKEY>` |
| T1 (must) | DB URIs avec creds embarquées | Redact | `<REDACTED:DB_URI>` |
| T1 (must) | Clés privées SSH | Redact | `<REDACTED:SSH_KEY>` |
| T2 (recommended) | Adresses email | Normaliser | `<REDACTED:EMAIL>` |
| T2 (recommended) | Adresses IP | Normaliser | `<REDACTED:IP>` |
| T2 (recommended) | Adresses MAC | Normaliser | `<REDACTED:MAC>` |
| T2 (recommended) | `/home/mickael` dans les paths | Normaliser | `~` |
| T3 (keep) | Noms de projets (lyra, roxabi-\*) | Conserver | — |
| T3 (keep) | Chemins sous `~/projects/` | Conserver | — |
| T3 (keep) | Numéros d'issues/PRs | Conserver | — |
| T3 (keep) | Branches git | Conserver | — |
| T3 (keep) | Noms de plugins/skills | Conserver | — |
| T4 (keep) | Usernames GitHub, "Mickael" | Conserver | — |

### Fallback layers (appliqués après trufflehog, dans l'ordre)

1. **Regex layer** : patterns pour Telegram (`\d{8,10}:[A-Za-z0-9_-]{35}`), NATS NKEYs (`^[SU][A-Z2-7]{56}$`), AWS (`AKIA[0-9A-Z]{16}`), JWTs (`eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`), bearer (`(?i)bearer\s+[A-Za-z0-9\-._~+/]{20,}`), Discord (`[MNO][A-Za-z0-9_-]{23}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27}`), Anthropic (`sk-ant-[A-Za-z0-9\-]{40,}`), OpenAI (`sk-[A-Za-z0-9]{48}`).
2. **Shannon entropy fallback** : chaînes base64-shaped (alphabet `[A-Za-z0-9+/=]`, longueur ≥20) avec H > 4.5 bits/char → `<REDACTED:HIGH_ENTROPY>`.

### Truncation anchor

Tout span tronqué dans `events.payload_json` porte des métadonnées inline :

```
<TRUNCATED source_file="~/.claude/projects/lyra/abc123.jsonl" offset=1048576 original_hash="sha256:deadbeef" lines_total=1200 kept_head=50 kept_tail=50>
```

Si l'analyste LLM (Phase 2) flague un span ambigu, le contenu brut est récupérable via `(source_file, offset)`.

### Validation gates

Après la sanitization pass :
1. Re-lancer trufflehog sur `~/.cortex/sanitized/` → doit retourner 0 findings.
2. 10-span spot-check manuel (sample aléatoire depuis `sanitization_log`).
3. Determinism check : re-run sur même input → diff de `sanitization_log` doit être vide.

---

## De-Noising Pass

S'exécute dans le même stream que la sanitization (stage 3).

### Event types supprimés

| Type | Raison |
|------|--------|
| `permission-mode` | Boilerplate infra, ¬signal |
| `ai-title` | Auto-généré, ¬signal d'intention |
| `last-prompt` | Doublon du user turn |
| `hookInfos` | Métadonnées internes de hook |

### Règles de truncation par outil

| Outil | Conservé | Supprimé |
|-------|---------|---------|
| Read | path + line_range + file_size + 10 premières lignes + 10 dernières (si fichier < 200 lignes) | corps du fichier |
| Bash | cmd + exit_code + stderr (complet) + stdout head-50 + tail-50 si > 5 KB | milieu des gros stdout |
| Grep | query + match_count + 10 premiers matches | matches restants |
| Glob | pattern + count + 20 premiers résultats | résultats restants |
| Edit / Write | fichier + diff complet | — (les diffs sont toujours du signal) |
| WebFetch / WebSearch | URL + HTTP status + premier 1 KB | corps restant |

**Exception (TOUJOURS conserver le résultat complet) :** `exit_code != 0` OU présence de : `error`, `Error`, `Exception`, `Traceback`, `command not found`, `No such file`, `ImportError`, `ModuleNotFoundError`, `AttributeError`, `is not defined`, `Permission denied`, `FAILED`, `AssertionError`. Ces signaux sont l'input primaire pour RC-2 et RC-7.

### Boilerplate dedup

Contenu CLAUDE.md / memory / system-reminder → hash SHA256 → stocké une seule fois dans `boilerplate.json` à `~/.cortex/boilerplate.json` → occurrences inline remplacées par `<BOILERPLATE:sha256[:8]>`.

---

## Episode Segmentation

### Champs d'un épisode

```
Episode {
  id:                   VARCHAR   (ulid)
  project:              VARCHAR
  intent:               VARCHAR   (voir taxonomie)
  started_at:           BIGINT    (epoch ms)
  ended_at:             BIGINT | NULL
  branch:               VARCHAR
  cwd:                  VARCHAR
  orchestrator_skill:   VARCHAR | NULL
  outcome:              VARCHAR   (default PENDING)
  files_touched_count:  INTEGER
  token_estimate:       BIGINT
  user_correction_count: INTEGER
  sub_agent_count:      INTEGER
  pr_number:            INTEGER | NULL
  issue_number:         INTEGER | NULL
  session_ids:          JSON      (array)
  source_tool_use_id:   VARCHAR | NULL
  outcome_classified_at: BIGINT
  trace_outcome:        VARCHAR   (success|failure|partial|null)
}
```

### Algorithme de segmentation (pseudocode)

```python
def segment_episodes(events: Iterator[Event]) -> Iterator[Episode]:
    current: Episode | None = None
    orchestrator_active: bool = False
    orchestrator_stack: list[str] = []

    ORCHESTRATOR_SKILLS = {
        "dev-core:dev", "dev-core:fix", "dev-core:promote",
        "dev-core:cleanup-context", "dev-core:1b1", "dev-core:loop"
    }
    IDLE_GAP_MINUTES = 30  # tunable ; désactivé par défaut (config.idle_gap_enabled = False)

    for event in events:
        # Détecter l'activation d'un orchestrator skill
        if event.event_type == "skill_attribution":
            if event.skill_name in ORCHESTRATOR_SKILLS:
                # Nouvel orchestrator → fermer l'épisode courant, ouvrir nouveau
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)
                orchestrator_active = True
                orchestrator_stack = [event.skill_name]
            elif orchestrator_active:
                # Sub-skill à l'intérieur d'un orchestrator → absorber, PAS de boundary
                pass
            else:
                # Changement de skill non-orchestrator sans orchestrator actif → boundary
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)

        elif event.event_type in ("branch_change", "cwd_change"):
            if orchestrator_active:
                # Absorber — dev-core:dev ouvre de nouvelles sessions par phase ; un seul épisode logique
                current.branch = event.new_value if event.event_type == "branch_change" else current.branch
                current.cwd = event.new_value if event.event_type == "cwd_change" else current.cwd
            else:
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)

        elif event.event_type == "session_start":
            if can_merge(current, event):
                # Même branch + même cwd + orchestrator actif → fusionner dans épisode courant
                current.session_ids.append(event.session_id)
            else:
                if current is not None:
                    yield finalize(current)
                current = new_episode(event)

        elif event.event_type == "subagent_start":
            current.sub_agent_count += 1
            # Les sessions subagent sont liées via source_tool_use_id
            # et traitées comme leurs propres épisodes avec FK vers le parent

        else:
            accumulate(current, event)

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
        session_start.git_branch == current.branch
        and session_start.cwd == current.cwd
        and current.orchestrator_skill is not None
        and gap_minutes(current.last_event_ts, session_start.ts) < MERGE_WINDOW_MINUTES
    )
```

Invariant clé : **quand un orchestrator est actif, les changements de branch/cwd ne ferment PAS l'épisode.** Le flow `/dev #N` ouvre de nouvelles sessions par phase (frame/spec/plan/implement) mais constitue un seul épisode logique.

LLM segmenter (Phase 2 uniquement) : traite les spans résiduels où `can_merge` est ambigu (mismatch de branch + pas d'orchestrator actif + gap < 60 min).

---

## Intent Taxonomy

20 intents. Classification automatique depuis le champ `attributionSkill` du JSONL (présent dans ≥80% des sessions). `freeform` est le seul bucket nécessitant le LLM residue classifier.

| Intent | Signal source | Skill / pattern de branch |
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
| `freeform` | tout le reste (catch-all) | LLM residue classifier (Phase 2) |

**[NEEDS CLARIFICATION: Q1]** Taux de présence du champ `attributionSkill` dans les JSONL existants — confirmé « présent dans le schéma JSONL » mais le nom exact du champ et le taux de présence sur les 5 657 fichiers nécessitent vérification au premier ingest V1. Si absent dans les sessions plus anciennes, la taxonomie tombe en fallback sur les heuristiques de nom de branch + `freeform`.

---

## Outcome Classifier

### 8-State Enum

| Outcome | Définition |
|---------|-----------|
| `SUCCESS_CLEAN` | CI green + ≤1 review iter + pas de rollback dans la fenêtre 2 semaines + pas d'incident prod |
| `SUCCESS_PIVOT` | Supersession d'ADR avec framing positif (design changé pour le mieux) |
| `PARTIAL_REVIEW_LOOPS` | Succès mais > 1 review iter |
| `PARTIAL_PROD_ISSUES` | Succès mais petit incident prod suivi |
| `PARTIAL_DESIGN_THRASH` | Convergé mais spec/ADR back-and-forth intense |
| `FAILED_LOOPS` | Cap de 3 iters review atteint avec bloqueurs non résolus (signal RC-5) |
| `FAILED_PROD_NIGHTMARE` | Incident prod + multiples rollbacks |
| `PENDING` | < 12h après `episode.ended_at` |

### Signal sources

| Signal | Source | Maps to |
|--------|--------|---------|
| Résultat CI | `pr_state.ci_status` | SUCCESS vs PARTIAL/FAILED |
| Nombre d'itérations de review | `pr_state.review_iter_count` | PARTIAL_REVIEW_LOOPS / FAILED_LOOPS |
| Bloqueurs non résolus au merge | `pr_state.has_unresolved_blockers` | FAILED_LOOPS |
| Commit de revert sur la branch | `git_events.is_revert` dans la fenêtre lookahead | FAILED_PROD_NIGHTMARE |
| Issue ré-ouverte après fermeture | `issue_events.event_type = "reopened"` | PARTIAL_PROD_ISSUES |
| Supersession d'ADR + label positif | `git_events.message ~= "supersede.*ADR"` | SUCCESS_PIVOT |
| Pas de PR liée | outcome dérivable depuis git seulement | SUCCESS_CLEAN (heuristique) |

### Algorithme de classification

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

### Re-classification nightly

Cron job (ou `insight classify --rerun`) : re-évalue les épisodes PENDING + SUCCESS où :
- `git_events.is_revert` est arrivé après la classification initiale.
- `pr_state.review_iter_count` a augmenté.
- `issue_events.event_type = "reopened"` est arrivé.

---

## Detector Pack v1

### Tier A — Regex + Compteurs (D1-D8)

Tous opèrent contre les tables `events` et `metrics`.

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
            results = [e.tool_result_hash for e in window]
            if len(set(results)) == 1:  # résultats identiques
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
                return None  # vérification trouvée

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
    files_edited: dict[str, int] = {}
    files_read: dict[str, int] = {}

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
    metric = db.get_metrics(episode_id)
    if not metric.intent_token_median:
        return None  # médiane pas encore calculée ; skip
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
    # error_flag est précalculé à l'ingest (payload_json.error_flag)
    error_events = db.get_error_events(episode_id)
    hallucination_hits = [
        evt for evt in error_events
        if HALLUCINATION_PATTERNS.search(evt.payload_json.get("tool_result") or "")
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
    """Détecteur cross-épisodes — tourne contre tous les épisodes de la fenêtre."""
    # tool_args_hash stocké dans payload_json pour les events JSONL-lane
    sigs = db.query("""
        SELECT
            json_extract(payload_json, '$.tool_name') as tool_name,
            json_extract(payload_json, '$.tool_args_hash') as tool_args_hash,
            COUNT(DISTINCT episode_id) as ep_count
        FROM events
        WHERE type = 'tool_use'
          AND json_extract(payload_json, '$.event_subtype') = 'permission_prompt'
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

**[NEEDS CLARIFICATION: Q2]** Nom exact du type d'event `permission_prompt` dans le schéma JSONL Claude Code — à vérifier lors du premier ingest V1.

---

### Tier B — Cross-Source (D9-D12)

Nécessitent les tables `pr_state` + `git_events` peuplées.

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
    Pour chaque épisode dev-core:fix suivi d'un épisode de code-review
    sur le même PR, vérifie si la review a trouvé de NOUVEAUX findings
    absents de la review précédente.
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
    # autres : médiane globale comme fallback
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
        path = extract_path(evt.payload_json.get("tool_args") or "")
        if not path:
            continue
        dirname = os.path.dirname(path)
        generator_files = db.list_files_in_dir(dirname)
        has_generator = any(GENERATOR_PATTERNS.search(f) for f in generator_files)
        if has_generator:
            regen_found = any(
                e.type == "tool_use"
                and json_extract(e.payload_json, "$.tool_name") == "Bash"
                and re.search(r"gen-|regen|make.*gen|python.*gen|uv run.*gen",
                              json_extract(e.payload_json, "$.tool_args") or "")
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
    Cluster les épisodes par (skill_sequence_signature, file_glob_pattern).
    Surface les clusters stables avec haut taux de succès comme candidats à l'automatisation.
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
        stable = sequence_stability(steps) >= 0.8
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

### Détecteurs déférés à v1.5

| ID | Nom | Raison |
|----|-----|--------|
| D13 | `fix_blast_radius` (RC-6) | Nécessite un catalogue d'anti-patterns curé d'abord |
| D14 | `parallel_paths_drift` (RC-3) | Nécessite un registre de parallel-paths d'abord |

### Détecteurs déférés à Phase 2 (LLM requis)

| ID | Nom | RC/Proposal |
|----|-----|------------|
| — | `silent_edits` | C3 |
| — | `reasoning_action_mismatch` | C7 |
| — | `sycophancy_upstream` | U4 |
| — | `instruction_decay` | C4 |
| — | `overcomplicated_solution` | C10 |

### Matrice de couverture RC

| RC | Description | Détecteurs |
|----|-------------|-----------|
| RC-1 | Même agent auteur et testeur | D2 (verification gap) |
| RC-2 | Paires générateur/source sans direction imposée | D3, D7, D12 |
| RC-3 | Parallel paths drift | D14 (v1.5) |
| RC-4 | Bash comme langage security-critical | D7 (hallucinated symbol couvre les erreurs bash) |
| RC-5 | Cap review à 3 itérations | D1, D9 |
| RC-6 | Scope d'un finding = point pas pattern (blast radius) | D11, D13 (v1.5) |
| RC-7 | Fix-pass introduit des défauts net-new | D2, D10 |

---

## Production d'Observations

Après la détection, insight encode chaque finding en `Observation` typée (contrat ADR-005) et la publie sur le sujet NATS `roxabi.memory.observations.publish` (contrat ADR-006).

### Mapping finding → Observation

Une `Observation` est produite par finding. Schema complet dans `roxabi-contracts.memory` (ADR-006).

```python
def encode_finding_as_observation(finding: Finding, episode: Episode) -> Observation:
    return Observation(
        id=ulid(),
        source="claude-code-jsonl",
        source_ref=finding.id,               # ID natif du finding
        timestamp=finding.created_at,
        category=ObservationCategory.FINDING,
        actors=[
            ActorRef(role="detector", ref=finding.detector_id),
            ActorRef(role="episode",  ref=episode.id),
            ActorRef(role="project",  ref=episode.project),
        ],
        topic=[finding.rc_mapping] if finding.rc_mapping else [],
        sentiment=severity_to_sentiment(finding.severity),
                                             # high → negative | medium → neutral | low → neutral
        payload_typed={
            "detector_id":    finding.detector_id,
            "severity":       finding.severity,
            "evidence":       finding.evidence,
            "example_turns":  finding.example_turns,
            "remediation":    finding.remediation,
            "rc_mapping":     finding.rc_mapping,
        },
        correlation={
            "episode_id":  episode.id,
            "project":     episode.project,
            "intent":      episode.intent,
            "outcome":     episode.outcome,
            "run_id":      finding.run_id,
        }
    )
```

### Sujet NATS

```
roxabi.memory.observations.publish
```

Défini dans `roxabi-contracts.memory` (ADR-006). Insight publie ; memory subscribe via le Retain Job.

### Lien avec memory

Insight ne fait que publier. La consolidation (résolution des actors en entités, dedup, schema_fit, decay update) est entièrement dans cortex-memory. Cf. `spec-cortex-memory.md` — section Retain Job.

---

## PR ↔ Episode Linkage

Stack de méthodes, premier match gagne :

| Priorité | Méthode | Source |
|----------|---------|--------|
| 1 | `episode.branch` correspond à `pr_state.head_branch` | gh PR list |
| 2 | SHA de commit d'épisode présent dans les commits PR | `git log` + gh PR commits |
| 3 | Numéro d'issue dans le nom de branch (ex. `1036-fix-shell-injection`) → trouver le PR pour cette issue | gh issue / PR cross-ref |
| 4 | Références de fichiers artifact | v1.5 |

---

## DuckDB Schema (côté insight)

Storage : `~/.cortex/insight.duckdb` (cf. ADR-011). Schéma détaillé futur : `docs/insight/DATA-MODEL.md` (à scinder depuis `docs/DATA-MODEL.md` actuel).

### `episodes`

```sql
CREATE TABLE episodes (
    id                    VARCHAR PRIMARY KEY,
    project               VARCHAR NOT NULL,
    intent                VARCHAR NOT NULL,
    started_at            BIGINT NOT NULL,
    ended_at              BIGINT,
    branch                VARCHAR,
    cwd                   VARCHAR,
    orchestrator_skill    VARCHAR,
    outcome               VARCHAR DEFAULT 'PENDING',
    outcome_classified_at BIGINT,
    pr_number             INTEGER,
    issue_number          INTEGER,
    files_touched_count   INTEGER DEFAULT 0,
    token_estimate        BIGINT DEFAULT 0,
    user_correction_count INTEGER DEFAULT 0,
    sub_agent_count       INTEGER DEFAULT 0,
    trace_outcome         VARCHAR
);
```

### `events`

Table générique multi-lane. Les champs spécifiques à une source (tool_name, tool_args_hash, error_flag, correction_flag, etc.) vivent dans `payload_json` — pas de colonnes racine JSONL-centric. Seule exception : `lane` (source-tag) qui est une colonne de premier niveau.

```sql
CREATE TABLE events (
    id            BIGINT PRIMARY KEY,
    episode_id    VARCHAR REFERENCES episodes(id),
    session_id    VARCHAR,
    parent_uuid   VARCHAR,
    timestamp     BIGINT NOT NULL,
    type          VARCHAR NOT NULL,    -- user | assistant | tool_use | tool_result | system
    payload_json  JSON,               -- contenu sanitisé + tronqué · schéma spécifique à la source
    raw_offset    BIGINT,
    raw_file      VARCHAR,
    lane          VARCHAR NOT NULL,   -- 'jsonl' | 'git' | 'nats' | 'mail' | 'telegram' | …
    nats_subject  VARCHAR,            -- peuplé pour lane='nats'
    trace_id      VARCHAR             -- ContractEnvelope.trace_id (lane='nats')
);
```

Note : `tool_name`, `tool_args_hash`, `error_flag`, `correction_flag` sont dans `payload_json` pour les events lane=jsonl, pas au niveau racine. Les détecteurs qui en ont besoin utilisent `json_extract(payload_json, '$.tool_name')`.

### `metrics`

```sql
CREATE TABLE metrics (
    episode_id         VARCHAR PRIMARY KEY REFERENCES episodes(id),
    tool_count         INTEGER DEFAULT 0,
    edit_count         INTEGER DEFAULT 0,
    test_count         INTEGER DEFAULT 0,
    failure_count      INTEGER DEFAULT 0,
    retry_count        INTEGER DEFAULT 0,
    review_iter_count  INTEGER DEFAULT 0,
    duration_ms        BIGINT,
    intent_token_median INTEGER             -- peuplé par calibrate
);
```

### `detection_runs` + `findings`

```sql
CREATE TABLE detection_runs (
    id                   VARCHAR PRIMARY KEY,
    started_at           BIGINT NOT NULL,
    completed_at         BIGINT,
    detector_set         VARCHAR,
    sanitization_version VARCHAR,
    config_json          JSON
);

CREATE TABLE findings (
    id               BIGINT PRIMARY KEY,
    run_id           VARCHAR REFERENCES detection_runs(id),
    episode_id       VARCHAR REFERENCES episodes(id),
    detector_id      VARCHAR NOT NULL,
    confidence       DOUBLE,
    severity         VARCHAR,
    event_id_start   BIGINT,
    event_id_end     BIGINT,
    evidence_text    TEXT,
    remediation_type VARCHAR,
    rc_mapping       VARCHAR,
    created_at       BIGINT NOT NULL,
    kind             VARCHAR DEFAULT 'raw',
    observation_id   VARCHAR             -- ULID de l'Observation publiée à memory (nullable avant publish)
);
```

### `patterns` (D15 — clustering)

```sql
CREATE TABLE patterns (
    id                   BIGINT PRIMARY KEY,
    name                 VARCHAR,
    detector_id          VARCHAR,
    episode_count        INTEGER,
    success_count        INTEGER,
    sample_episode_ids   JSON
);
```

### `pr_state`, `git_events`, `issue_events`

```sql
CREATE TABLE pr_state (
    pr_number         INTEGER,
    repo              VARCHAR,
    head_branch       VARCHAR,
    state             VARCHAR,
    ci_status         VARCHAR,
    review_iter_count INTEGER,
    has_unresolved_blockers BOOLEAN DEFAULT FALSE,
    merged_at         BIGINT,
    fetched_at        BIGINT,
    PRIMARY KEY (repo, pr_number)
);

CREATE TABLE git_events (
    id            BIGINT PRIMARY KEY,
    sha           VARCHAR,
    repo          VARCHAR,
    branch        VARCHAR,
    timestamp     BIGINT,
    message       TEXT,
    is_revert     BOOLEAN DEFAULT FALSE,
    files_touched JSON,
    episode_id    VARCHAR REFERENCES episodes(id)
);

CREATE TABLE issue_events (
    id            BIGINT PRIMARY KEY,
    issue_number  INTEGER,
    repo          VARCHAR,
    event_type    VARCHAR,
    actor         VARCHAR,
    occurred_at   BIGINT,
    episode_id    VARCHAR REFERENCES episodes(id)
);
```

### `sanitization_log`

```sql
CREATE TABLE sanitization_log (
    id                      BIGINT PRIMARY KEY,
    raw_file                VARCHAR,
    redaction_count_by_type JSON,
    truncation_bytes_saved  BIGINT,
    boilerplate_dedups      INTEGER,
    sanitized_at            BIGINT
);
```

### Calibration tables

```sql
CREATE TABLE calibration_runs (
    id                 VARCHAR PRIMARY KEY,
    version            VARCHAR NOT NULL,
    started_at         BIGINT NOT NULL,
    completed_at       BIGINT,
    sample_size        INTEGER NOT NULL,
    sample_episode_ids JSON,
    labeling_method    VARCHAR,
    status             VARCHAR
);

CREATE TABLE calibration_labels (
    id              BIGINT PRIMARY KEY,
    cal_run_id      VARCHAR REFERENCES calibration_runs(id),
    episode_id      VARCHAR REFERENCES episodes(id),
    detector_id     VARCHAR NOT NULL,
    true_positive   BOOLEAN NOT NULL,
    detector_fired  BOOLEAN NOT NULL,
    label_source    VARCHAR,
    notes           TEXT
);

CREATE TABLE calibration_metrics (
    cal_run_id       VARCHAR REFERENCES calibration_runs(id),
    detector_id      VARCHAR NOT NULL,
    precision        DOUBLE,
    recall           DOUBLE,
    f1               DOUBLE,
    n_pos            INTEGER,
    n_neg            INTEGER,
    threshold_p_min  DOUBLE,
    threshold_r_min  DOUBLE,
    passed           BOOLEAN,
    PRIMARY KEY (cal_run_id, detector_id)
);
```

---

## Validation & Calibration Strategy

### Bootstrap protocol

1. `insight calibrate --sample-size 50` tire un échantillon stratifié :
   - 10 épisodes × 5 classes d'intention (dev-lifecycle, implement-feature, fix-findings, code-review, freeform)
   - Balancé selon les classes d'outcome (SUCCESS / PARTIAL / FAILED / PENDING)
2. Pour chaque épisode samplisté : exécuter tous les détecteurs → collecter `{episode_id, detector_id, fired: bool}`.
3. LLM bootstrap (Kimi via fireworks.ai) : envoyer résumé de l'épisode de-noised + hypothèse détecteur → LLM retourne `{detector_id, expected: bool, confidence: 0-1}`.
4. `--save-labels FILE` : sauvegarder les labels LLM bruts pour spot-check.
5. Spot-check humain : uniquement les désaccords où `LLM.confidence > 0.7` ET `detector.fired != LLM.expected` → queue plafonnée à 20 items.
6. P/R calculé par détecteur ; stocké dans la table `calibration_metrics`.

### Seuil de shipping

| Condition | Décision |
|-----------|---------|
| P >= 0.7 AND R >= 0.5 | Ship |
| P >= 0.7 AND R < 0.5 (détecteur high-leverage) | Ship avec note de justification dans l'appendice de calibration |
| P < 0.7 | Hold ; ajuster le détecteur, re-calibrer |

High-leverage = détecteur mappé sur RC avec impact cross-projet (RC-2, RC-5, RC-7 qualifient).

### Cadence de re-calibration

- Mensuelle pour les 3 premiers mois.
- Trimestrielle ensuite.
- Trigger : taux de firing d'un détecteur change > 20% semaine sur semaine (alerte automatique dans le rapport).

---

## CLI Grammar — `insight`

```
insight [OPTIONS] COMMAND [ARGS]
```

### Commandes

```
insight watch
  # mode continu : toutes lanes (file watcher cocoindex JSONL + poll git/gh + NATS subscriber)

insight ingest
  --since DATE         ISO-8601 ou relatif (7d, 2w, 2025-03-24)
  --until DATE         default: now
  --projects LIST      noms de projets séparés par virgule (default: all)
  --lane LANE          filtrer par lane: jsonl | git | nats | all (default: all)
  --dry-run            reporter ce qui serait ingéré, ¬écrire en DB
  --workers N          workers de sanitization parallèles (default: 4)

insight detect
  --episodes-only      exécuter seulement les détecteurs scoped épisode (skip D8, D10, D15)
  --detectors LIST     liste séparée par virgule (ex. D1,D2,D7) ; default: all
  --rerun              effacer les findings existants pour les détecteurs sélectionnés, recalculer
  --since DATE
  --until DATE

insight classify
  --llm-residue-only   skip le classifier rule-based, LLM seulement sur PENDING avec signaux ambigus
  --rerun              re-classifier tous les épisodes non-PENDING
  --since DATE

insight report
  --top N              cap findings par section (default: 10)
  --output PATH        fichier de sortie ; default stdout
  --format md|html|json  default: md
  --since DATE
  --until DATE
  --project NAME

insight compare WINDOW1 WINDOW2
  --metric METRIC      métrique spécifique (ex. D1_rate, cost_outlier_pct)
  WINDOW1 / WINDOW2: "2025-03-24:2025-04-07" ou "last-week" | "this-week" | "last-2w"

insight automation
  --min-cluster-size N   default: 5
  --min-success-rate R   float 0.0-1.0, default: 0.70
  --output PATH

insight calibrate
  --sample-size N        default: 50
  --save-labels FILE
  --load-labels FILE
  --llm-model MODEL      default: kimi (via litellm)
```

### Config file

`~/.cortex/insight.toml` :

```toml
[paths]
raw_corpus     = "~/.claude/projects/"
sanitized_dir  = "~/.cortex/sanitized/"
db_path        = "~/.cortex/insight.duckdb"

[sanitize]
trufflehog_bin = "~/.local/bin/trufflehog"
t2_redact      = true

[segment]
idle_gap_enabled       = false
idle_gap_minutes       = 30
merge_window_minutes   = 120

[detect]
d5_cost_outlier_ratio   = 3.0
d6_ctx_token_threshold  = 150000
d8_permission_threshold = 5
d15_min_cluster_size    = 5
d15_min_success_rate    = 0.70

[llm]
provider    = "fireworks"
model       = "accounts/fireworks/models/kimi-k2-5"
max_tokens  = 1024
temperature = 0.1
enabled     = false    # Phase 2 uniquement ; opt-in explicite

[nats]
url        = "nats://localhost:4222"
creds_file = "~/.config/lyra/nats.creds"
subscribe  = ["lyra.jobs.*", "lyra.results.*", "lyra.progress.*",
              "lyra.llm.generate.*", "lyra.voice.*", "lyra.conversation.>"]
publish_observations = "roxabi.memory.observations.publish"
```

---

## Rapport — Structure

### Sections

| # | Section | Contenu |
|---|---------|---------|
| 1 | Executive summary | période, nombre d'épisodes, top-3 détecteurs par fréquence |
| 2 | Améliorations semaine sur semaine | détecteurs dont le taux a baissé vs période précédente |
| 3 | Régressions | détecteurs dont le taux a augmenté |
| 4 | Patterns efficaces | classes d'intention avec taux SUCCESS_CLEAN ≥ 80% |
| 5 | Patterns inefficaces | classes d'intention avec taux FAILED ≥ 20% |
| 6 | Candidats à l'automatisation | clusters D15 (nom de skill suggéré + liste d'étapes) |
| 7 | Findings par détecteur | classés par score ; ≤10 findings par détecteur |
| 8 | Appendice de calibration | P/R actuel par détecteur ; nombre de labels |

### Formule de ranking

```
score(finding) = normalize(frequency) × severity_weight × actionability_weight

où :
  frequency        = nombre d'épisodes pour ce détecteur dans la fenêtre de rapport
  severity_weight  = {"high": 1.0, "medium": 0.6, "low": 0.3}[finding.severity]
  actionability    = 1.0 si finding.remediation is not None else 0.5
  normalize(x)     = x / max_frequency_in_window   (0.0–1.0)
```

---

## Breadboard / Vertical Slices

### Slice V1 — Tracer bullet : 1 jour → 1 épisode en DuckDB

**Goal :** pipeline end-to-end qui fonctionne pour les données d'un seul projet. Pas de détecteurs.
**Demo :** `insight ingest --since 1d --projects lyra` → `episodes` a ≥1 ligne.

AC :
- [ ] `insight ingest --since 1d --projects lyra` exit 0.
- [ ] Table `episodes` a ≥1 ligne.
- [ ] Table `sanitization_log` a ≥0 lignes.
- [ ] Re-lancer la même commande est idempotent (pas de doublons).

### Slice V2 — Sanitization complète + validation gates

**Goal :** redaction T1+T2 complète, trufflehog validation passe, determinism check passe.
**Demo :** `insight ingest --since 7d --dry-run` → rapporte les comptes de redaction, 0 findings trufflehog sur l'output.

AC :
- [ ] trufflehog re-scan de `~/.cortex/sanitized/` retourne 0 findings.
- [ ] Script de spot-check 10-span exit 0.
- [ ] Re-run produit `sanitization_log` identique (determinism).
- [ ] Redaction T2 : email/IP/MAC/home-path fonctionnels.

### Slice V3 — Détecteurs Tier A (D1-D8) + table findings

**Goal :** les 8 détecteurs Tier A tournent contre les épisodes ingérés, findings stockés.
**Demo :** `insight detect` → table findings peuplée ; au moins D2 fire sur fixture connue.

AC :
- [ ] D1-D8 s'exécutent sans erreur sur les fixtures de test.
- [ ] D2 fire sur `session_fix_no_verify.jsonl` (écriture sans appel test suivant).
- [ ] D7 fire sur `session_hallucinated_symbol.jsonl` (ImportError dans tool result).
- [ ] Table `findings` peuplée avec les bonnes valeurs `rc_mapping`.
- [ ] `insight detect --detectors D2` exécute uniquement D2.

### Slice V4 — Jointure multi-source + détecteurs Tier B (D9-D12)

**Goal :** git log + données GitHub PR ingérées, détecteurs Tier B opérationnels.
**Demo :** `insight detect --detectors D9,D10,D12` sur un épisode lyra avec review loop connu → D9 fire.

AC :
- [ ] Table `git_events` peuplée pour au moins 1 projet.
- [ ] Table `pr_state` peuplée via CLI `gh` pour les PRs liées.
- [ ] D9 fire pour épisode avec `pr.review_iter_count >= 3 AND has_unresolved_blockers`.
- [ ] D12 fire sur fixture `session_generator_drift.jsonl`.
- [ ] Linkage épisode-PR : au moins méthode 1 (branch match) fonctionnelle.

### Slice V5 — Outcome classifier + re-classification nightly

**Goal :** tous les épisodes classifiés ; PENDING résolu au fil de l'arrivée des signaux.
**Demo :** `insight classify` sur les épisodes lyra des 2 dernières semaines → aucun PENDING pour les épisodes > 12h.

AC :
- [ ] `insight classify` exit 0.
- [ ] Tous les épisodes > 12h ont outcome ≠ PENDING.
- [ ] `insight classify --rerun` met à jour les outcomes quand de nouvelles données git/gh changent le signal.
- [ ] SUCCESS_CLEAN, PARTIAL_REVIEW_LOOPS, FAILED_LOOPS apparaissent tous dans les résultats.

### Slice V6 — Report + compare

**Goal :** `insight report` produit un output lisible et classé. `insight compare` calcule des deltas.
**Demo :** `insight report --since 7d --format md` → rapport complet avec section appendice de calibration.

AC :
- [ ] Rapport a les 8 sections.
- [ ] Bloc finding montre ≤3 IDs de session + citation 1 ligne.
- [ ] Formule de score appliquée ; détecteurs triés par score descendant.
- [ ] `insight compare last-week this-week` produit une table de delta.
- [ ] `--format json` produit du JSON valide avec clés `findings`, `patterns`, `calibration`.

### Slice V7 — Candidats à l'automatisation D15 + calibration

**Goal :** détection de clusters D15 opérationnelle ; boucle de calibration bootstrapée.
**Demo :** `insight automation` sur le corpus 6 semaines → ≥1 cluster avec nom de skill suggéré.

AC :
- [ ] `insight automation` exit 0 sur le corpus 6 semaines.
- [ ] Au moins 1 pattern surfacé si le corpus est assez grand.
- [ ] `insight calibrate --sample-size 10 --save-labels /tmp/labels.json` exit 0.
- [ ] Valeurs P/R écrites dans l'appendice de calibration au prochain `insight report`.

---

## Phasing (scope insight)

| Phase | Ajoute dans insight | Coût LLM |
|---|---|---|
| 1 | Lane 1+2 ingest · D1-D15 · outcome classifier · rapport behavioral · encode+publish Observation (Finding) | $0 |
| 1.5 | Lane 3 NATS adapter · raw events lane-tagged multi-source | $0 |
| 2 | LLM analyst (Kimi) · intent freeform residue · LLM bootstrap calibration | ~$10-30/run |
| 3 | Longitudinal compare · correction latency read depuis memory | ~$1-5/run |
| 4 | GEPA detector evolution · pipelines relationship (mail + Telegram) | TBD |

---

## Contraintes

- Python 3.13 (`.python-version` pin dans `packages/insight/`).
- `uv` + `hatchling` build backend.
- Pas de modèles Anthropic comme juges (biais same-model). Phase 2 : Kimi/GLM via fireworks.ai.
- `trufflehog --no-verification` (jamais `--verification`).
- Pas d'appels API live pendant la sanitization.
- DuckDB à `~/.cortex/insight.duckdb` (cf. ADR-011).
- `nats-py >= 2.7` pour le subscriber NATS.
- `roxabi-contracts` depuis le monorepo Lyra via uv GitHub source.
- CLI doit fonctionner sur M₁ (Ubuntu Server 24.04+) et M₂ (Pop!_OS, dev).
- Containerisé Podman + Quadlet (cf. ADR-002) : `ghcr.io/roxabi/cortex-insight:staging`.
- `cortex_insight.*` ne peut pas importer `cortex_memory.*` (cf. ADR-008).

---

## Open Questions

**Q1** — Taux de présence du champ `attributionSkill` dans les JSONL existants (voir section Intent Taxonomy).

**Q2** — Nom exact du type d'event `permission_prompt` dans le schéma JSONL Claude Code (voir D8).

**Q3** — Source du token estimate : le JSONL Claude Code peut inclure ou non des champs `usage` par turn. Si absent, estimation en fallback : 1 token ≈ 4 chars.

**Q4** — Mode d'arrivée par source (ADR-007, statut `open`) : à décider source par source à l'implémentation. Actuellement : JSONL = hook (cocoindex file watcher), git/gh = pull périodique, NATS = push.

**Q5** — `lyra.conversation.*` sujet NATS (Q17 du SP original) : pas encore dans `roxabi-contracts`. Le subscriber Lane 3 skip cette famille de sujets jusqu'à ce que l'ADR correspondant dans le repo Lyra soit mergé.
