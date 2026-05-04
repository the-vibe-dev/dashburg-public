# NodeHealth

NodeHealth is the operational view over RemoteOps node health and host monitor data.

## Inputs
- RemoteOps node inventory
- runner heartbeat and service probes
- optional host monitor endpoint

## Optional host monitor configuration
Set:
- `HOST_MONITOR_BASE_URL`
- `HOST_MONITOR_TOKEN`

Example:
```bash
HOST_MONITOR_BASE_URL=http://host-monitor.example.local:19444
HOST_MONITOR_TOKEN=change-me
```
