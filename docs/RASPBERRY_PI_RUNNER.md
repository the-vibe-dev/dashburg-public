# Raspberry Pi Runner

Raspberry Pi uses the standard Linux runner path in this repo.

Recommended notes:
- use a 64-bit Raspberry Pi OS image
- ensure Python venv support is installed
- keep concurrency conservative on smaller boards
- disable unnecessary job types if memory is tight

Install:
```bash
cd runner
./scripts/deploy_runner_node.sh
sudo ./scripts/install_runner.sh
```
