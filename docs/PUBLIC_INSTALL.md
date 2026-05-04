# Public Install Walkthrough

## 1. Clone both repos
```bash
cd ~/apps
git clone https://github.com/the-vibe-dev/dashburg-public.git dashgithub
git clone https://github.com/the-vibe-dev/dashburg-modules.git dashburg-modules
```

## 2. Run the guided installer
```bash
cd ~/apps/dashgithub
./scripts/install_dashgithub.sh
```

The installer prepares:
- `backend/.venv`
- `runner/.venv`
- `web/node_modules`
- `.env`
- `runner/config.yaml`

## 3. Start the base host
API:
```bash
./scripts/start_dashburg_backend.sh
```

Runner:
```bash
cd runner
./.venv/bin/python run.py
```

Frontend:
```bash
./scripts/start_dashburg_frontend.sh
```

## 4. Install optional modules
UI:
- open `Settings -> Add Modules`

CLI:
```bash
./scripts/manage_modules.sh install ideavault
./scripts/manage_modules.sh install topic-insights
```

## 5. Bootstrap bundled runtimes
Single runtime:
```bash
./scripts/bootstrap_module_runtime.sh topic-insights
```

All installed bundled runtimes:
```bash
./scripts/bootstrap_module_runtime.sh all
```

Direct CLI equivalent:
```bash
./scripts/manage_modules.sh runtime-bootstrap-all
```

## 6. Validate
```bash
./scripts/manage_modules.sh validate topic-insights
./scripts/manage_modules.sh runtime-status topic-insights
./scripts/manage_modules.sh runtime-service-status topic-insights
```

## 7. Review ports
- API: `http://127.0.0.1:8431`
- Runner: `http://127.0.0.1:8444`
- Frontend: `http://127.0.0.1:4174`

## Notes
- `webagent` and `schedule-ops` rely on the host plus local runner rather than a separate bundled API.
- `discord-control`, `topic-insights`, `trends-researcher`, and `skilled-agents` now run locally on the installed device, but still need their own local credentials or provider config to do useful work.
