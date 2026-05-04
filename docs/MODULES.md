# Module Runtime Guide

`dashburg-public` installs optional modules from the sibling `dashburg-modules` repo.

Install action:
- copies module files into the host repo
- enables host UI/backend registration

Runtime action:
- may also require starting a bundled local service on the same device

## Runtime modes
- `host-only`: no extra local service required beyond the Dashburg host
- `bundled-local-service`: module pack includes a local backend/service source tree that must be installed and started on the same device
- `local-runner-node`: module uses the local Dashburg runner instead of a separate backend
- `host-and-runner`: module uses the public host plus the local runner

## Module map
- `topic-insights`: bundled local service on `127.0.0.1:8080`
- `idea-factory`: uses local `topic-insights` runtime
- `ideavault`: host-local, optional handoff into local `topic-insights`
- `trends-researcher`: bundled local service on `127.0.0.1:8400`
- `skilled-agents`: bundled local service on `127.0.0.1:8787`
- `discord-control`: bundled local bridge on `127.0.0.1:9101`
- `webagent`: local runner node
- `schedule-ops`: host + local runner

## Module instructions
Read the README in each module pack under `~/apps/dashburg-modules/<module>/README.md`.
