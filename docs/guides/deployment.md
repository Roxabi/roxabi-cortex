---
title: Deployment Guide
description: Podman + Quadlet deployment for cortex-insight and cortex-memory.
---

# Deployment Guide

Both services deploy via **Podman + Quadlet** (systemd --user), consistent with the Lyra/voiceCLI pattern. See [ADR-002](../adr/ADR-002-deployment-podman-quadlet.md) for full rationale.

## Environments

| Environment | Host | Auto-deploy? | Restart policy |
|---|---|:---:|---|
| Production | M₁ (roxabituwer, 192.168.1.16, 24/7) | No | `autorestart=true` via systemd |
| Dev | M₂ (ROXABITOWER, on-demand) | No | manual, no auto-restart |

Both environments use the same Quadlet units — no environment-specific Dockerfiles.

## Service Images

| Service | Image | Quadlet unit |
|---|---|---|
| cortex-insight | `ghcr.io/roxabi/cortex-insight:staging` | `packages/insight/deploy/quadlet/cortex-insight.container` |
| cortex-memory | `ghcr.io/roxabi/cortex-memory:staging` | `packages/memory/deploy/quadlet/cortex-memory.container` |

## Ops Commands

```bash
# Start
make cortex-insight start
make cortex-memory start

# Stop
make cortex-insight stop
make cortex-memory stop

# Reload (restart after config/image change)
make cortex-insight reload
make cortex-memory reload

# Status
make cortex-insight status
make cortex-memory status

# Logs (tail)
make cortex-insight logs
make cortex-memory logs
```

Behind the scenes, `make` delegates to `systemctl --user {start,stop,restart,status} cortex-{insight,memory}.service`.

> TODO: Replace Makefile stubs with real `systemctl --user` calls once Quadlet units are installed.

## Installing Quadlet Units

```bash
# Copy units to systemd user dir
cp packages/insight/deploy/quadlet/cortex-insight.container ~/.config/containers/systemd/
cp packages/memory/deploy/quadlet/cortex-memory.container  ~/.config/containers/systemd/

# Reload systemd daemon
systemctl --user daemon-reload

# Verify units are visible
systemctl --user list-units cortex-*.service
```

## Podman Secrets (NATS nkeys)

```bash
# Create secrets (one-time per machine)
podman secret create nkey-cortex-insight <path-to-nkey-file>
podman secret create nkey-cortex-memory  <path-to-nkey-file>
```

NEVER put nkeys in `.env` or Quadlet `Environment=` directives.

## Network

Both services join `roxabi.network` (shared Podman network used by Lyra). The NATS server is reachable at `lyra-nats:4222` from within that network.

```bash
# Verify network exists
podman network ls | grep roxabi

# Create if missing (usually created by lyra deployment)
podman network create roxabi.network
```

## Storage

DuckDB files are bind-mounted from the host:

| Service | Host path | Mount |
|---|---|---|
| cortex-insight | `~/.cortex/insight.duckdb` | read-write |
| cortex-memory | `~/.cortex/memory.duckdb` | read-write |

```bash
# Create data dir (one-time)
mkdir -p ~/.cortex
```

## Hardening

Applied to all Roxabi containers (ADR-002, following ADR-053/054 from lyra):

```ini
NoNewPrivileges=true
ReadOnlyRootfs=true
DropCapability=all
UserNS=keep-id:uid=1500,gid=1500
```

## Build & Push

> TODO: Document CI pipeline (GitHub Actions → GHCR push) once workflow is written.

```bash
# Local build for testing
podman build -t ghcr.io/roxabi/cortex-insight:staging packages/insight/
podman build -t ghcr.io/roxabi/cortex-memory:staging packages/memory/
```

## See Also

- [ADR-002](../adr/ADR-002-deployment-podman-quadlet.md) — deployment decision + template reference
- [Configuration](../standards/configuration.md) — env vars and secrets
- [Troubleshooting](troubleshooting.md) — service won't start, NATS issues
