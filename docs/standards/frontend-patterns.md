---
title: Frontend Patterns
description: N/A — roxabi-cortex has no frontend.
---

# Frontend Patterns

**N/A — roxabi-cortex has no frontend component.**

`cortex-insight` and `cortex-memory` are Python CLI + NATS worker services. There is no web UI, no browser client, and no HTTP framework. See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full service topology.

## AI Quick Reference

- NEVER spawn a `frontend-dev` agent for this project — no frontend exists.
- NEVER add an HTTP framework or web server to either service.
- ALWAYS refer to [ARCHITECTURE.md](../ARCHITECTURE.md) for the correct service shape (CLI + NATS).
