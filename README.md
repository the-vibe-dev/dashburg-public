# Dashgithub

Dashgithub is the reduced public-control-plane extraction of Dashburg with an installable module system.

## Built-in Surface
- `TaskVault` (`projects`)
- `Memory`
- `RemoteOps`
- `NodeHealth`
- `LocalOps`
- `MailCenter`
- `Orchestration`
- `Settings`

## Optional Modules
Optional modules are discovered from the sibling repo `../dashburg-modules` and can be installed from:
- the UI: `Settings -> Add Modules`
- the CLI: `./scripts/manage_modules.sh`

Packaged modules:
- `ideavault`
- `idea-factory`
- `topic-insights`
- `trends-researcher`
- `discord-control`
- `webagent`
- `skilled-agents`
- `schedule-ops`

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

## Module Management
List catalog entries:
```bash
./scripts/manage_modules.sh list
```

Install a module and its dependencies:
```bash
./scripts/manage_modules.sh install ideavault
```

Validate a module:
```bash
./scripts/manage_modules.sh validate ideavault
```

Optional module packs live in:
```bash
~/apps/dashburg-modules
```

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
