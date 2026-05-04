# Dashgithub

Dashgithub is the reduced public-control-plane extraction of Dashburg.

It keeps the operational surface for:
- `TaskVault` (`projects`)
- `Memory`
- `RemoteOps`
- `NodeHealth`
- `LocalOps`
- `MailCenter`
- `Orchestration`
- `Settings`

It excludes the broader internal factory, browser automation, Discord, video, and other custom product surfaces from the source repo.

## Stack
- Backend: FastAPI + SQLModel + SQLite
- Frontend: React + TypeScript + Vite + Tailwind
- Worker: Dashgithub runner (`runner/`)

## Review Ports
- API: `8431`
- Runner: `8444`
- Frontend: `4174`

## Setup
```bash
cd ~/apps/dashgithub
./scripts/install_dashgithub.sh
```

Manual setup:
```bash
cd ~/apps/dashgithub/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cd ~/apps/dashgithub/web
npm install

cd ~/apps/dashgithub/runner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then adjust paths, tokens, and shared-memory settings.

## Start For Review
API:
```bash
cd ~/apps/dashgithub
./scripts/start_dashburg_backend.sh
```

Runner:
```bash
cd ~/apps/dashgithub/runner
./.venv/bin/python run.py
```

Frontend:
```bash
cd ~/apps/dashgithub
./scripts/start_dashburg_frontend.sh
```

## RemoteOps Requirements
- `examples/servers.yaml` or `DASHBURG_REMOTEOPS_INVENTORY`
- runner shared secrets and per-node config
- a valid SSH key for terminal sessions
- `DASHBURG_SHARED_MEMORY_ROOT` if you want cross-node memory/orchestration context
- runner mailbox cron/bootstrap scripts for MailCenter and Orchestration flows

## Included Docs
- `docs/remoteops_easy_setup.md`
- `docs/localops.md`
- `docs/SHARED_MEMORY.md`
- `docs/ORCHESTRATION.md`
- `docs/NODEHEALTH.md`
- `docs/WINDOWS_RUNNER.md`
- `docs/RASPBERRY_PI_RUNNER.md`
