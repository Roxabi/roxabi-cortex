---
title: Testing Standards
description: pytest layout, fixtures, and test conventions for cortex-insight and cortex-memory.
---

# Testing Standards

> Universal patterns (Testing Trophy, mock boundaries, coverage anti-patterns) are embedded in the `tester` agent.
> This file documents **cortex-specific** testing setup.

## Framework

| Tool | Purpose |
|---|---|
| pytest | unit + integration tests |
| pyright | type checking (run separately, not via pytest) |
| ruff | linting (run separately) |

No e2e framework (no HTTP server, no browser). Integration tests mount both containers + a local NATS instance.

## Layout

```
packages/
├── insight/
│   └── tests/
│       ├── conftest.py          # fixtures: tmp DuckDB, sample raw events, mock NATS
│       ├── unit/
│       │   ├── test_ingest_*.py   # one file per source parser
│       │   ├── test_pipeline_*.py # behavioral pipeline tests
│       │   └── test_encode_*.py   # Observation encoding
│       └── integration/
│           └── test_ingest_flow.py  # raw → sanitize → DuckDB → publish
└── memory/
    └── tests/
        ├── conftest.py          # fixtures: tmp DuckDB, sample Observations, mock NATS
        ├── unit/
        │   ├── test_retain.py     # Retain Job consolidation logic
        │   ├── test_graph.py      # entity/relation CRUD + decay
        │   └── test_assemble.py   # context retrieval
        └── integration/
            └── test_observation_flow.py  # subscribe → retain → graph update
```

## Running Tests

```bash
# All tests (from workspace root)
uv run pytest

# One package
uv run pytest packages/insight/tests/

# Unit only
uv run pytest packages/insight/tests/unit/

# With coverage
uv run pytest --cov=cortex_insight packages/insight/tests/
```

## Fixture Conventions

- `tmp_duckdb` — pytest fixture providing a fresh DuckDB at a temp path; teardown drops the file.
- `mock_nats` — mock NATS client that captures published messages without a live server.
- `sample_raw_event` — factory fixture for `RawEventEnvelope` instances (parameterized by source).
- `sample_observation` — factory fixture for `Observation` instances (parameterized by category).

> TODO: Populate `conftest.py` files with these fixtures during Phase 1 implementation.

## Mocking Strategy

| What | How |
|---|---|
| DuckDB | `tmp_duckdb` fixture — real DuckDB at `tmp_path`, dropped after test |
| NATS | `mock_nats` fixture — mock client, captures published messages |
| File watcher (cocoindex) | monkeypatch or inject a test event iterator |
| External sources (mail IMAP, Telegram) | stub factories that emit `RawEventEnvelope` |

NEVER mock the module under test. NEVER mock DuckDB with an in-memory dict — use a real DuckDB temp file.

## Coverage

> TODO: Set coverage thresholds after Phase 1 implementation is underway. Suggested baseline: 70% line coverage minimum; 90% for Retain Job and encode modules.

## AI Quick Reference

- ALWAYS use a `tmp_duckdb` fixture — NEVER use the real `~/.cortex/*.duckdb` in tests.
- NEVER mock the module under test; mock its dependencies (NATS, DuckDB, file sources).
- ALWAYS co-locate fixtures in `conftest.py` of the relevant package — NEVER define fixtures in test files.
- PREFER parameterized tests for source-specific parser variations over copy-pasted test functions.
