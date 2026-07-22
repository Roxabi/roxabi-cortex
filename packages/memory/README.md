# cortex-memory (MVP)

Long-term memory **NATS satellite** for Roxabi (ADR-087).

## Surface

| Subject | Role |
|---|---|
| `roxabi.memory.capture` | put knowledge entry |
| `roxabi.memory.query.search` | full-text search |
| `roxabi.memory.query.assemble` | context block for agents |
| `roxabi.memory.heartbeat` | satellite heartbeat |

Contracts: `roxabi_contracts.memory` (factory monorepo).

## Run

```bash
cd packages/memory
uv sync

# import legacy vault (optional)
uv run cortex-memory import-vault   # ~/.roxabi-vault/vault.db → ~/.cortex/memory.db

# serve NATS workers
export NATS_URL=nats://127.0.0.1:4222
uv run cortex-memory serve
```

## Factory wiring

Factory always uses `CortexVault` (no vault CLI fallback):

```bash
export NATS_URL=nats://127.0.0.1:4222
uv run cortex-memory serve
# factory hub: /vault-add, /search, bare URLs + first-turn assemble → NATS
```

Production provision (nkeys + Quadlet): see
`roxabi-factory/docs/runbooks/cortex-memory.md`.

## Deps

`roxabi-contracts` + `roxabi-nats` — currently **path** sources to local
`~/projects/roxabi-factory/packages/*` until the memory contracts land on
`staging` tags; then switch `[tool.uv.sources]` to git+subdirectory like voiceCLI.
