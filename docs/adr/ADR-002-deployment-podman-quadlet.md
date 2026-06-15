---
adr: ADR-002
title: Déploiement — Podman + Quadlet (cohérent écosystème Roxabi)
status: accepted
date: 2026-05-06
deciders: mickael
supersedes: -
superseded_by: -
related: [ADR-001, ADR-008]
tags: [deployment, infra, podman, quadlet, security]
---

## Contexte

Initialement présumé que cortex-insight et cortex-memory tourneraient comme « services Python supervisés » directement (uv + supervisord). Vérification dans l'écosystème existant :

| Service | Forme réelle |
|---|---|
| lyra (hub, telegram, discord, clipool, nats) | image `ghcr.io/roxabi/lyra:staging` · 5 Quadlet `.container` units · réseau Podman `roxabi.network` · secrets Podman pour nkeys |
| voiceCLI (tts, stt) | images `ghcr.io/roxabi/voicecli-{tts,stt}` · Quadlet · base `ghcr.io/roxabi/ml-base` |
| llmCLI, imageCLI | Dockerfile présent · pattern identique |
| Hardening | `NoNewPrivileges`, `ReadOnly`, `DropCapability=all`, `UserNS=keep-id` (ADR-053/054 lyra) |

Les confs supervisord héritées de l'ancien pattern existent encore mais sont en transition (certaines vides). Le pattern actif et cible = Podman + Quadlet + systemd.

## Décision

Déployer cortex-insight et cortex-memory sous le **même pattern que les services Lyra/voiceCLI** :

| Aspect | Choix |
|---|---|
| Build | `Dockerfile` dans chaque package · multi-stage · base `ghcr.io/roxabi/base:latest` |
| Image | `ghcr.io/roxabi/cortex-insight:staging` · `ghcr.io/roxabi/cortex-memory:staging` |
| Deploy | Quadlet `.container` units dans `packages/<svc>/deploy/quadlet/` |
| Lifecycle | systemd (Quadlet auto-translaté) sur prod (M₁) · idem sur dev (M₂) |
| Réseau | join `roxabi.network` Podman pour parler à `lyra-nats:4222` |
| Secrets | Podman secrets pour nkeys NATS (`nkey-cortex-insight`, `nkey-cortex-memory`) |
| Hardening | `NoNewPrivileges=true`, `ReadOnly=true`, `DropCapability=all`, `UserNS=keep-id:uid=1504,gid=1504` |
| Storage | DuckDB en bind mount `%h/.cortex/{insight,memory}.duckdb` (persistance hors image) |
| Ops user-facing | `make cortex-insight {start,stop,reload,logs}` + idem memory · jamais `supervisorctl` ni `podman` direct |

## Conséquences

| Aspect | Impact |
|---|---|
| Cohérence | aligné sur le pattern unique Roxabi · pas d'exception infra |
| Sécurité | hardening obligatoire dès la première image (¬retrofit later) |
| CI | nécessite pipeline build → push GHCR (à mettre en place) |
| Réseau | dépendance dure au réseau `roxabi.network` et au service `lyra-nats` |
| Dev local M₂ | idem prod (Quadlet) · simplifie le diff prod/dev |

## Alternatives écartées

| Option | Pourquoi rejetée |
|---|---|
| Service Python supervisé direct (mon erreur initiale) | ¬cohérent avec le reste de l'écosystème · perd hardening Podman · perd isolation rootless |
| Docker au lieu de Podman | écosystème Roxabi est Podman · pas de raison de fork |
| Kubernetes | overkill pour single-host solo · ajoute friction massive |

## Notes

L'image base `ghcr.io/roxabi/base:latest` fournit déjà Python 3.12 + uv + setup commun. Cortex peut hériter sans coût additionnel. Le bind mount des fichiers DuckDB doit être inline `Volume=` (pattern lyra-hub) — les `.volume` units wrappant un fichier unique peuvent faillir silencieusement.

Voir `lyra/deploy/quadlet/lyra-hub.container` comme template de référence.
