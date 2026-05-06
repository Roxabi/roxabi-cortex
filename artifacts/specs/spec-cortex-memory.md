---
title: spec-cortex-memory
status: draft
date: 2026-05-06
related_adrs: [ADR-001, ADR-002, ADR-003, ADR-005, ADR-006, ADR-008, ADR-009, ADR-010, ADR-011]
related_specs: [spec-cortex-insight]
superseded_by: -
needs_clarification: [ADR-009]
---

## Context

**cortex-memory** est le service `warehouse + consolidation` de l'écosystème **roxabi-cortex** (ADR-001).

Architecture d'ensemble : `docs/ARCHITECTURE.md`. Décisions structurantes :

| ADR | Sujet | Impact direct sur memory |
|---|---|---|
| ADR-003 | Lake/warehouse split | memory = warehouse · ne parse pas le brut · reçoit uniquement des `Observation` typées |
| ADR-005 | Contrat `Observation` | memory consolide les observations reçues (Retain Job) · insight encode |
| ADR-006 | `roxabi-contracts` extension | `memory.py` = `Observation` + subjects query + actuate |
| ADR-008 | Monorepo workspace | `packages/memory/` dans `roxabi-cortex/` · ¬import de `cortex_insight` |
| ADR-009 | Taxonomie des entités | **DEFERRED** — bloque le schéma final du graphe · section dédiée ci-dessous |
| ADR-010 | Cohabitation Lyra | **DEFERRED** — Lyra en mode producteur seul en attendant |
| ADR-011 | DuckDB v1 + triggers KuzuDB | `~/.cortex/memory.duckdb` · OLTP/graphe · triggers de revisit |
| ADR-002 | Podman + Quadlet | `ghcr.io/roxabi/cortex-memory:staging` · `roxabi.network` |

Frontière avec insight : memory ne lit jamais `insight.duckdb`. Il reçoit des `Observation` typées via NATS `roxabi.memory.observations.publish` et répond aux requêtes sur `roxabi.memory.query.*`.

---

## [NEEDS CLARIFICATION: ADR-009] — Taxonomie des entités

> **Cette section sera réécrite après résolution d'ADR-009.**

ADR-009 (statut : `deferred`) fixera la taxonomie complète des types d'entités du graphe — namespacing, axes (type mémoire Tulving × référent), handlers du Retain Job par catégorie d'observation, templates de Compiled Truth.

**À ce stade**, la taxonomie héritée du SP original est conservée comme **placeholder** :

| Type | Sous-types | Namespace actuel (placeholder) |
|------|-----------|-------------------------------|
| `behavioral` | detector, rc, pattern, episode | `detector:D1`, `rc:RC-2`, `pattern:<slug>` |
| `world` | project, person, concept, decision | `project:lyra`, `person:mickael` |
| `instruction` | claude_md, memory_entry, skill, allowlist | `skill:dev-core:dev`, `claude_md:<section>` |
| `nats` | llm_call, job, turn | `job:<trace_id>`, `turn:<id>` |

**La taxonomie sera refondue** via l'interview biomimétique (cf. ADR-009 — cadres Tulving, phénoménologie, Speech Act Theory, ToM). Elle passera probablement à un namespacing path-style `world:person:anya`, `self:mickael:rc:RC-2`, `agent:claude-code:pattern:X`. Cette refonte conditionne également l'écriture de `docs/memory/DATA-MODEL.md` final.

**Issue de tracking** : à créer lors de la session d'interview biomimétique.

---

## Goal

Recevoir les `Observation` typées produites par insight, les consolider dans un graphe vivant (entités + relations avec decay), maintenir la Compiled Truth par entité, servir les consommateurs (Claude Code `/dev assemble`, Lyra recall, reports), et actionner les diffs approuvés (CLAUDE.md / skills / memory PRs).

**L'asset long-terme = le graphe dans `memory.duckdb`.** Tout le reste (parsers, pipelines, détecteurs dans insight) est remplaçable. Le graphe est régénérable depuis le raw event log si nécessaire.

---

## 4-Layer Memory Architecture

Mapping vers la topologie cortex :

| Layer | Hébergement | Rôle |
|-------|------------|------|
| **Layer 1 — Raw** | cortex-insight (`insight.duckdb`) | Raw event log append-only · lane-tagged · toutes sources |
| **Layer 2 — Knowledge Graph** | cortex-memory (`memory.duckdb`) | Entités + relations + decay · dedup · schema_fit |
| **Layer 3 — Compiled Truth** | cortex-memory (`memory.duckdb`) | Per-entity markdown · regen nightly · versioned |
| **Layer 4 — Actuation** | cortex-memory (`memory.duckdb`) | Approval queue · auto-PR · human gate |

Ce spec couvre les Layers 2-4. Le Layer 1 est défini dans `spec-cortex-insight.md`.

### Layer 2 — Knowledge Graph

Entités + relations avec decay temporel. Schéma dans la section DuckDB ci-dessous.

**Types d'entités (placeholder — ADR-009) :**
- Behavioral : Detector, RC, Pattern, Episode, Outcome
- World : Project, Person, Concept, Decision
- Instruction : CLAUDEmd-section, MemoryEntry, Skill, Allowlist
- NATS-derived : LlmCall, Job, Turn

**Types de relations :** `fires_in`, `maps_to`, `co_occurs`, `remediated_by`, `supersedes`, `triggered_by`, `resulted_in`, `uses_model`, `costs`, `decided_in`, `reinforces`

### Layer 3 — Compiled Truth

Per-entity markdown, régénéré nightly via impact analysis. `impact.py` détermine quelles entités ont changé (Δ`memory_strength` > `regen_threshold`). `truth.py` régénère `body_md` pour les entités affectées. Les versions sont conservées ; `superseded_by` FK chaîne l'historique.

Config : `regen_threshold = 0.1` (changement de 10% de memory_strength déclenche la regen).

### Layer 4 — Actuation

Approval queue + auto-PR. Human gate avant tout diff CLAUDE.md/skill/memory.

1. `truth.py` émet un diff → ligne `approval_queue` (status=pending)
2. `memory approve` liste les items pending ; l'utilisateur approuve/rejette
3. `memory publish` — items approuvés → `actuate/pr.py` → auto-PR sur le repo cible
4. Config : `auto_pr = false` (publish explicite requis)

---

## Memory Strength Model

Adapté du modèle hippo-memory (bio-inspiré). Remplace la formule bare `exp(-Δt/σ)`.

### Formule de strength

```
strength(t) = base_strength
              × (0.5 ^ (Δt / effective_half_life))
              × retrieval_boost
              × emotional_multiplier

où :
  Δt                  = jours depuis last_reinforced
  reward_factor       = 1 + 0.5 × ((outcome_pos - outcome_neg) / (outcome_pos + outcome_neg + 1))
                        plage : (0.5, 1.5)
  effective_half_life = half_life_days × reward_factor
  retrieval_boost     = 1 + (0.1 × log₂(retrieval_count + 1))
  emotional_multiplier = neutral:1.0 | positive:1.3 | negative:1.5 | critical:2.0
```

### Mapping severity → emotional_valence

| Severity du finding | emotional_valence | Multiplicateur | Effet |
|---|---|---|---|
| high | critical | 2.0 | half-life doublée à la base ; entité persiste bien plus longtemps |
| medium | negative | 1.5 | half-life ×1.5 |
| low | neutral | 1.0 | Decay nominal |

### Table d'ajustement de half-life

| Signal | Modificateur |
|---|---|
| Chaque requête d'entité (`retrieval_count++`) | +2j half-life de base (via retrieval_boost) |
| `emotional_valence=critical` | ×2.0 half-life de base |
| `schema_fit > 0.7` (RC connu — fast-track) | ×1.5 (consolide vite) |
| `schema_fit < 0.3` (novel — dark matter bucket) | ×0.5 (s'efface vite si non utilisé) |
| Chaîne `outcome_positive` → adoption rate ≥ 0.7 | `reward_factor` jusqu'à 1.5× |
| Chaîne `outcome_negative` → pas d'amélioration post-merge | `reward_factor` down to 0.5× |
| `pinned = TRUE` (verrouillé par l'utilisateur) | Infini — pas de decay |

### Modes de decay

| Mode | Usage |
|---|---|
| `clock` | Temps wall-clock ; simple, prévisible |
| `session` | Decay par nombre de cycles de sommeil ; pour usage intermittent d'un projet |
| `adaptive` | Scale la half-life par l'intervalle moyen de session par projet (défaut) |

`adaptive` est le défaut : les projets que Mickael ouvre quotidiennement décayent à taux nominal ; les projets ouverts mensuellement auto-étendent leur half-life ×30. Pas de config par projet nécessaire.

### Schema fit

Calculé au moment du Retain Job (heuristique, pas de LLM). Jaccard IDF-pondéré sur les tags + overlap de tokens de contenu contre les entités existantes.

| Plage de schema_fit | Routing | Effet |
|---|---|---|
| > 0.7 | RC connu / pattern connu | Fast-track vers compiled truth ; half-life ×1.5 |
| 0.3 – 0.7 | Fit modéré | Consolidation normale |
| < 0.3 | Dark matter (pas de RC correspondant) | half-life ×0.5 ; survit uniquement via strength élevée ; LLM mine les survivants en Phase 2 |

### Reward feedback loop (ferme le cycle actuation)

```
finding fire (RC-2) → entity.outcome_positive++  (si edit CLAUDE.md mergé + taux de pattern ↓)
                    → entity.outcome_negative++  (si taux de pattern inchangé après merge)
→ reward_factor module effective_half_life
→ RC-2 remédiée avec succès décaye plus lentement (reste prominent)
→ RC-2 dont la remédiation n'a eu aucun effet décaye plus vite (signal auto-correctif)
```

---

## Memory Kind Envelope

Toute ligne de `findings` (publiée via Observation) et toute ligne de `compiled_truth` porte :

| kind | Signification | Cycle de vie |
|------|-------------|-------------|
| `raw` | Finding — append-only | Jamais directement supprimé ; archivage via `suppress=TRUE` → kind→`archived` |
| `distilled` | Corps de compiled truth (synthétisé) | Régénéré nightly ; version précédente → `superseded` |
| `superseded` | Version de compiled truth remplacée | Conservé pour l'analyse de tendance ; lié via `superseded_by` |
| `archived` | Supprimé par l'utilisateur (calibration) ou RGPD delete | Retiré du FTS ; snapshot raw_archive conservé |

---

## Retain Job

Le Retain Job vit dans cortex-memory. Il s'exécute à chaque `Observation` reçue sur `roxabi.memory.observations.publish` (contrat ADR-005 / ADR-006).

### Séquence de consolidation

Pour chaque `Observation` reçue :

1. **Résolution des actors** — chaque `ActorRef` dans `observation.actors` est résolu vers une entité existante (par slug ou par cosine similarity > 0.85) ou crée une nouvelle entité.
2. **Dedup contre le graphe** — si une entité très similaire existe (`schema_fit > 0.85`), les données sont fusionnées plutôt que dupliquées.
3. **Calcul de schema_fit** — Jaccard IDF-pondéré sur les tags + tokens de l'observation vs le corpus d'entités existantes.
4. **Détection de conflits** — cf. algorithme Conflict Detection ci-dessous.
5. **Écriture entités + relations** — upsert dans `entities` ; création/mise à jour des arêtes dans `relations`.
6. **Mise à jour memory_strength + decay** — recalcul `strength(t)` pour les entités touchées ; mise à jour de `last_reinforced`, `retrieval_count`, `emotional_valence`.
7. **Trigger regen compiled_truth** — si l'impact sur `memory_strength` d'une entité dépasse `regen_threshold` (0.1), planifier une regen de `compiled_truth` pour cette entité.

### Routing selon la catégorie d'Observation

La taxonomie des catégories d'`Observation` est partiellement définie dans ADR-005 ; le mapping complet vers les handlers du Retain Job dépend d'ADR-009 (deferred). Mapping actuel :

| category | Entités cibles (placeholder) | Handler |
|----------|------------------------------|---------|
| `finding` | Detector, RC, Pattern, Episode | `retain/handlers/behavioral.py` |
| `interaction` | Person, Project, Concept | `retain/handlers/relationship.py` (Phase 2+) |
| `decision` | Decision, CLAUDEmd-section | `retain/handlers/decision.py` (Phase 2+) |
| `artifact` | Skill, MemoryEntry | `retain/handlers/artifact.py` (Phase 2+) |

---

## Conflict Detection

Exécuté lors de la génération de la compiled truth et avant la promotion dans l'approval queue.

### Algorithme (hippo-adapted)

```python
def detect_conflict(entity_a: Entity, entity_b: Entity) -> bool:
    """
    Retourne True si les deux entités sont en conflit potentiel.
    """
    # 1. Stopword-filter les deux corps d'entités
    tokens_a = stopword_filter(entity_a.body_md)
    tokens_b = stopword_filter(entity_b.body_md)

    # 2. Jaccard sur les tokens restants
    intersection = set(tokens_a) & set(tokens_b)
    union        = set(tokens_a) | set(tokens_b)
    jaccard      = len(intersection) / len(union) if union else 0.0

    if jaccard < CONFLICT_OVERLAP_THRESHOLD:  # config: 0.5
        return False

    # 3. Vérification de la polarité sur les 40 premiers mots de chaque corps
    polarity_a = detect_polarity(entity_a.body_md[:POLARITY_WINDOW])  # config: 40 words
    polarity_b = detect_polarity(entity_b.body_md[:POLARITY_WINDOW])

    if polarity_a != polarity_b and polarity_a != "neutral" and polarity_b != "neutral":
        return True  # Jaccard élevé + polarité opposée = conflit

    return False
```

Si conflit détecté :
- `conflicts_with` JSON mis à jour sur les deux entités (array de slugs).
- Les items de l'approval queue en conflit sont flaggés ; résolution humaine obligatoire avant merge.

---

## Correction Latency

Auto-métrique de la couche actuation :

```
correction_latency = approval_queue.decided_at − observation.timestamp
```

Surfacé dans le digest hebdomadaire. Latence persistante élevée (> 14j) sur les findings HIGH severity → alerte de santé système dans le rapport.

---

## Compiled Truth — Impact Analysis + Regen

### Impact Analysis (`impact.py`)

Détermine quelles entités doivent être régénérées après chaque run du Retain Job :

```python
def compute_impacted_entities(retain_run_id: str, db: Store) -> list[str]:
    """Retourne les entity_ids dont memory_strength a changé de > regen_threshold."""
    return db.query("""
        SELECT entity_id
        FROM entity_strength_log
        WHERE retain_run_id = ?
          AND abs(strength_after - strength_before) > ?
    """, retain_run_id, REGEN_THRESHOLD)
```

### Regen (`truth.py`)

Pour chaque entité impactée, génère un nouveau `body_md` :

1. Récupère toutes les relations entrantes/sortantes de l'entité.
2. Agrège les findings récents (kind=raw, last 7j) verbatim.
3. Condense les findings plus anciens depuis la version précédente de compiled_truth.
4. Écrit une nouvelle ligne `compiled_truth` (version++).
5. Marque la version précédente `kind='superseded'` + `superseded_by = <new_id>`.

**Phase 2 :** LLM Kimi génère le `body_md` à partir du contexte agrégé (au lieu de templates statiques).

---

## Assemble — DAG-aware Context Retrieval

`assemble` est la fonction de récupération de contexte consommée par Claude Code `/dev` et Lyra recall via `roxabi.memory.query.assemble` (contrat ADR-006).

### Algorithme

```python
def assemble(
    goal: str | None,
    budget_tokens: int = 4000,
    fresh_tail_days: int = 7,
    eviction_policy: str = "bio",
) -> AssembleResponse:
    """
    DAG-aware context assembly.
    Levels : leaf (raw findings) → fact (entity summaries) → summary (compiled truth) → entity_profile
    """
    # 1. Boost des entités liées au goal actif (goal stack)
    if goal:
        boosted_slugs = get_goal_related_slugs(goal)
        boost_factor  = 3.0  # boost jusqu'à 3×
    else:
        boosted_slugs = []
        boost_factor  = 1.0

    # 2. Récupérer les findings récents verbatim (fresh tail)
    fresh_findings = db.query("""
        SELECT * FROM findings
        WHERE created_at > epoch_ms() - (? * 86400000)
          AND kind = 'raw'
        ORDER BY created_at DESC
    """, fresh_tail_days)

    # 3. Récupérer les compiled truths pour les entités avec strength élevée
    entity_profiles = db.query("""
        SELECT e.slug, ct.body_md, e.memory_strength
        FROM entities e
        JOIN compiled_truth ct ON ct.entity_id = e.id
        WHERE ct.id = (
            SELECT id FROM compiled_truth
            WHERE entity_id = e.id
            ORDER BY version DESC LIMIT 1
        )
        ORDER BY e.memory_strength DESC
    """)

    # 4. Construire le contexte jusqu'au budget
    context_items = []
    tokens_used   = 0

    for finding in fresh_findings:
        cost = estimate_tokens(finding)
        if tokens_used + cost > budget_tokens * (1 - DAG_OVERFLOW_CAP):
            break
        context_items.append(ContextItem(type="raw_finding", content=finding, tokens=cost))
        tokens_used += cost

    for profile in entity_profiles:
        cost = estimate_tokens(profile.body_md)
        slug_boost = boost_factor if profile.slug in boosted_slugs else 1.0
        effective_strength = profile.memory_strength * slug_boost

        if eviction_policy == "bio":
            # Éviction bio : lowest-strength évincé en premier
            # (la liste est déjà triée par strength DESC, donc on prend tant qu'il y a du budget)
            pass

        if tokens_used + cost <= budget_tokens:
            context_items.append(ContextItem(type="compiled_truth", content=profile.body_md,
                                             strength=effective_strength, tokens=cost))
            tokens_used += cost
        else:
            break  # budget épuisé

    return AssembleResponse(items=context_items, tokens_used=tokens_used, goal=goal)
```

Config :
- `fresh_tail_days = 7` — fenêtre verbatim (findings récents conservés intégralement)
- `budget_tokens = 4000` — budget de contexte par défaut
- `eviction_policy = "bio"` — lowest-strength évincé en premier
- `dag_overflow_cap = 0.3` — fraction max du budget pour les overflow summaries DAG

---

## Goal Stack (dlPFC model)

`/dev #N` = goal actif. Le goal conditionne le recall : les entités taguées avec l'issue/projet correspondant sont boostées jusqu'à 3× pendant l'assemble.

### Modèle

```python
class GoalPolicy(str, Enum):
    HYBRID             = "hybrid"
    ERROR_PRIORITIZED  = "error-prioritized"
    SCHEMA_FIT_BIASED  = "schema-fit-biased"
    RECENCY_FIRST      = "recency-first"
```

### Lifecycle d'un goal

```
goal push --name "issue:1234" --issue 1234 --project lyra
  → goal_stack row (status=active, retrieval_policy=hybrid)
  → assemble appels boostent les entités liées à issue:1234

goal complete --outcome 0.8
  → goal_stack.status = 'completed'
  → goal_stack.outcome_score = 0.8
  → propagation vers entity strength : les entités consultées pendant ce goal
    reçoivent outcome_positive++ si outcome_score > 0.5, outcome_negative++ sinon

goal suspend / goal resume
  → status = 'suspended' / 'active'
```

---

## DuckDB Schema (côté memory)

Storage : `~/.cortex/memory.duckdb` (cf. ADR-011). Workload OLTP/graphe. Migration conditionnelle vers KuzuDB si triggers atteints (latence assemble p95 > 200ms · contention · > 100k relations · > 10k entités).

Schéma détaillé futur : `docs/memory/DATA-MODEL.md` (à écrire après ADR-009 résolue).

### `entities`

```sql
CREATE TABLE entities (
    id                VARCHAR PRIMARY KEY,      -- ulid
    slug              VARCHAR UNIQUE NOT NULL,  -- "rc:RC-2" · "project:lyra" · "detector:D7"
    type              VARCHAR NOT NULL,          -- behavioral | world | instruction | nats (placeholder — ADR-009)
    subtype           VARCHAR,                  -- detector|rc|pattern|episode|project|person|…
    name              VARCHAR,
    -- Champs strength (hippo-memory model)
    memory_strength   DOUBLE DEFAULT 1.0,
    half_life_days    DOUBLE DEFAULT 30.0,
    retrieval_count   INTEGER DEFAULT 0,
    last_reinforced   BIGINT,
    outcome_positive  INTEGER DEFAULT 0,
    outcome_negative  INTEGER DEFAULT 0,
    emotional_valence VARCHAR DEFAULT 'neutral', -- neutral|positive|negative|critical
    schema_fit        DOUBLE DEFAULT 0.5,
    pinned            BOOLEAN DEFAULT FALSE,
    conflicts_with    JSON,                     -- array de slugs en conflit
    created_at        BIGINT NOT NULL,
    updated_at        BIGINT NOT NULL
);

-- Formule strength (cf. section Memory Strength Model)

CREATE UNIQUE INDEX entities_slug          ON entities(slug);
CREATE INDEX entities_type_subtype         ON entities(type, subtype);
CREATE INDEX entities_memory_strength      ON entities(memory_strength);
CREATE INDEX entities_schema_fit           ON entities(schema_fit);
CREATE INDEX entities_emotional_valence    ON entities(emotional_valence);
CREATE INDEX entities_pinned               ON entities(pinned) WHERE pinned = TRUE;
```

### `relations`

```sql
CREATE TABLE relations (
    id              VARCHAR PRIMARY KEY,  -- ulid
    source_id       VARCHAR NOT NULL REFERENCES entities(id),
    target_id       VARCHAR NOT NULL REFERENCES entities(id),
    type            VARCHAR NOT NULL,     -- fires_in|maps_to|co_occurs|remediated_by|supersedes|…
    weight_temporal DOUBLE DEFAULT 1.0,  -- exp(-Δt/σ) ; σ par type dans config [graph]
    weight_semantic DOUBLE DEFAULT 1.0,
    confidence      DOUBLE DEFAULT 0.9,
    last_observed   BIGINT NOT NULL,
    metadata_json   JSON
);

CREATE INDEX relations_source        ON relations(source_id);
CREATE INDEX relations_target        ON relations(target_id);
CREATE INDEX relations_type          ON relations(type);
CREATE INDEX relations_weight_temporal ON relations(weight_temporal);
```

### `compiled_truth`

```sql
CREATE TABLE compiled_truth (
    id             VARCHAR PRIMARY KEY,  -- ulid
    entity_id      VARCHAR NOT NULL REFERENCES entities(id),
    version        INTEGER NOT NULL,
    body_md        TEXT NOT NULL,
    source_obs_ids JSON,                 -- Observation IDs qui ont conduit à cette version
    generated_at   BIGINT NOT NULL,
    superseded_by  VARCHAR,             -- FK vers compiled_truth.id suivant
    kind           VARCHAR DEFAULT 'distilled'  -- distilled | superseded | archived
);

CREATE INDEX compiled_truth_entity  ON compiled_truth(entity_id);
CREATE INDEX compiled_truth_version ON compiled_truth(entity_id, version DESC);
```

### `approval_queue`

```sql
CREATE TABLE approval_queue (
    id           VARCHAR PRIMARY KEY,  -- ulid
    entity_id    VARCHAR REFERENCES entities(id),
    diff_type    VARCHAR NOT NULL,     -- claude_md | memory_entry | skill | allowlist
    diff_body    TEXT NOT NULL,
    target_path  VARCHAR NOT NULL,
    status       VARCHAR DEFAULT 'pending',  -- pending | approved | rejected
    created_at   BIGINT NOT NULL,
    decided_at   BIGINT
);

CREATE INDEX approval_queue_status ON approval_queue(status) WHERE status = 'pending';
CREATE INDEX approval_queue_entity ON approval_queue(entity_id);
```

### `buffer`

Mémoire de travail pour les Observations en cours de traitement. Les `Observation` arrivent ici avant que le Retain Job les consolide dans le graphe. Évite que le bruit contamine les calculs de decay des entités.

```sql
CREATE TABLE buffer (
    id            VARCHAR PRIMARY KEY,  -- ulid
    observation_id VARCHAR NOT NULL,   -- ULID de l'Observation reçue
    source        VARCHAR NOT NULL,    -- "claude-code-jsonl" | "mail" | …
    nats_subject  VARCHAR,
    trace_id      VARCHAR,
    payload_json  JSON,
    arrived_at    BIGINT NOT NULL,
    processed     BOOLEAN DEFAULT FALSE  -- TRUE après traitement par Retain Job
);

CREATE INDEX buffer_processed ON buffer(processed) WHERE processed = FALSE;
CREATE INDEX buffer_arrived   ON buffer(arrived_at);
```

### `goal_stack`

```sql
CREATE TABLE goal_stack (
    id                VARCHAR PRIMARY KEY,  -- ulid
    session_id        VARCHAR,
    goal_name         VARCHAR NOT NULL,     -- "issue:1234" | "lyra auth refactor"
    issue_number      INTEGER,
    project           VARCHAR,
    status            VARCHAR DEFAULT 'active',  -- active | suspended | completed
    retrieval_policy  VARCHAR DEFAULT 'hybrid',
    outcome_score     DOUBLE,
    created_at        BIGINT NOT NULL,
    completed_at      BIGINT
);

CREATE INDEX goal_stack_status ON goal_stack(status) WHERE status = 'active';
CREATE INDEX goal_stack_issue  ON goal_stack(issue_number) WHERE issue_number IS NOT NULL;
```

---

## NATS Subjects (côté memory)

Définis dans `roxabi-contracts.memory` (ADR-006).

| Subject | Direction | Usage |
|---------|-----------|-------|
| `roxabi.memory.observations.publish` | insight → memory | Retain Job subscribe · traitement de chaque Observation |
| `roxabi.memory.query.entities` | consommateurs → memory | Lookup d'entité par slug ou critères |
| `roxabi.memory.query.assemble` | consommateurs → memory | Claude Code `/dev`, Lyra recall |
| `roxabi.memory.query.compiled` | consommateurs → memory | Récupérer la compiled truth d'une entité |
| `roxabi.memory.actuate.approve` | ops → memory | Opérations sur l'approval queue |

---

## CLI Grammar — `memory`

Ces commandes font partie du CLI `cortex-memory` (package séparé dans `packages/memory/`).

```
memory entity SLUG
  # Lookup graphe pour l'entité par slug
  # Output : champs de l'entité + relations + memory_strength actuelle

memory compiled SLUG
  # Afficher la compiled truth (body_md) pour l'entité
  # --version N   version spécifique (default: latest)
  # --history     lister toutes les versions

memory approve
  # Lister l'approval queue (status=pending) ; approuver ou rejeter interactivement
  # --diff-type TYPE  filtrer par type (claude_md | skill | memory_entry | allowlist)

memory publish
  # Items approuvés → actuate/pr.py → auto-PR sur le repo cible
  # --dry-run        afficher les diffs sans créer de PR

assemble
  --budget N           budget en tokens pour la fenêtre de contexte (default: 4000)
  --fresh-tail-days N  fenêtre verbatim pour les findings récents (default: 7)
  --goal SLUG          conditionner l'assembly sur le goal actif (booste les entités correspondantes)
  --format md|json     default: md
  # Output : bloc de contexte DAG-aware — findings récents verbatim + findings plus anciens
  #          comme résumés compiled_truth + éviction bio-aware (lowest-strength en premier si over budget)

goal push
  --name TEXT
  --issue N
  --project NAME
  --policy hybrid|error-prioritized|schema-fit-biased|recency-first

goal list

goal complete
  --outcome 0.0-1.0    # propage l'outcome score aux entity strengths

goal suspend

goal resume
```

---

## Phasing (scope memory)

| Phase | Ajoute dans memory | Coût LLM |
|---|---|---|
| 1.5 | Retain Job · buffer · entities + relations · goal_stack · assemble basique | $0 |
| 2 | Decay adaptatif + consolidation nightly · Layer 3 Compiled Truth (templates statiques) · DAG-aware assemble complet · dark matter LLM mining | ~$10-30/run |
| 3 | Layer 4 Actuation (approval queue + auto-PR) · conflict detection · correction latency · propagation outcome→entity strength | ~$1-5/run |
| 4 | GEPA sur les sections CLAUDE.md · sujets `lyra.memory.*` live · merge corpus multi-host | TBD |

---

## Contraintes

- Python 3.13 (`.python-version` pin dans `packages/memory/`).
- `uv` + `hatchling` build backend.
- DuckDB à `~/.cortex/memory.duckdb` (cf. ADR-011).
- Triggers de revisit memory → KuzuDB : latence assemble p95 > 200ms · contention writes/reads observée · > 100k relations · > 10k entités.
- `nats-py >= 2.7` pour le subscriber NATS.
- `roxabi-contracts` depuis le monorepo Lyra via uv GitHub source.
- CLI doit fonctionner sur M₁ (Ubuntu Server 24.04+) et M₂ (Pop!_OS, dev).
- Containerisé Podman + Quadlet (cf. ADR-002) : `ghcr.io/roxabi/cortex-memory:staging`.
- `cortex_memory.*` ne peut pas importer `cortex_insight.*` (cf. ADR-008).
- Instrumenter la latence assemble + lock waits dès la Phase 1.5 (sinon les triggers ADR-011 sont inopérants).

---

## Open Questions

**Q1** — Résolution ADR-009 (taxonomie) : interview biomimétique à planifier. Bloque `docs/memory/DATA-MODEL.md` final et la réécriture de la section taxonomie de ce spec.

**Q2** — ADR-010 (cohabitation Lyra) : deferred jusqu'à Phase 1 cortex opérationnel + ADR-009 résolue. En attendant : Lyra = producteur seul (publie ses events à insight, ne querie pas memory).

**Q3** — Résolution des entités : seuil cosine > 0.85 proposé pour l'auto-merge (cohérent avec le design lyra-memory). À valider contre le corpus réel avant activation. En dessous du seuil : entités restent séparées ; merge manuel via `memory approve`.

**Q4** — Decay adaptatif : `decay_basis=adaptive` nécessite `avg_session_interval_days` par projet, dérivé du corpus JSONL au premier ingest. Projets avec < 7 sessions utilisent `clock` en attendant l'historique suffisant.

**Q5** — Validation des seuils schema_fit : `schema_fit_fast_track=0.7` et `schema_fit_dark_matter=0.3` sont des valeurs proposées depuis les defaults hippo. À valider contre le corpus 6 semaines : `schema_fit < 0.3` route-t-il correctement les findings sans RC connu dans le dark matter bucket ?

**Q6** — Sujets NATS `lyra.memory.*` (Q18 du SP original) : nécessitent un ADR dans le repo Lyra avant que memory puisse publier des findings sur le bus. Bloqué jusqu'à Phase 4.

**Q7** — Namespacing et scoping des entités (cf. ADR-009) : sans namespacing, pas de scoping possible pour ADR-010 (ce qu'un agent tiers comme Lyra peut voir vs la mémoire personnelle de Mickael).
