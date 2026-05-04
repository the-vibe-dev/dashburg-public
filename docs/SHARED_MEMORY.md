# Shared Memory

Shared memory is optional but recommended for Memory, LocalOps, and Orchestration.

## Environment
```bash
DASHBURG_SHARED_MEMORY_ROOT=/mnt/shared/dashgithub
```

## Expectations
- the path must exist and be readable by the API process
- runner nodes should mount the same shared path if you want cross-node context
- if unset, the system falls back to local-only behavior where supported
