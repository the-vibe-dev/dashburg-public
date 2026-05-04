# RemoteOps Setup

This public repo assumes a hub-and-runner layout.

## Hub requirements
- Dashgithub API reachable by operators
- Dashgithub frontend reachable by operators
- shared inventory file or `DASHBURG_REMOTEOPS_INVENTORY`
- signing secrets shared with each runner

## Runner requirements
- Python 3.11+
- `runner/config.yaml` derived from `runner/config.example.yaml`
- a unique `node_id`
- a `shared_secret` matching the hub-side inventory entry

## Minimal inventory example
```yaml
servers:
  - id: hub
    base_url: http://127.0.0.1:8444
    key_id: hub-main
    secret_env: DASHGITHUB_RUNNER_SECRET_HUB
```

## Terminal host notes
If you use RemoteOps terminal sessions, provision:
- a dedicated SSH user
- an authorized key for the hub
- `REMOTEOPS_SSH_USER`
- `REMOTEOPS_SSH_KEY_PATH`
- `REMOTEOPS_TERMINAL_ENTRY`

The provided install script is:
- `runner/scripts/install_dashterm_main.sh`

Review the script before using it in production and replace placeholders for your environment.
