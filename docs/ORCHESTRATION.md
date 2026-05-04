# Orchestration

Orchestration coordinates runner jobs, mailbox work, and shared execution state.

## Depends on
- RemoteOps inventory and runner connectivity
- MailCenter mailbox records
- shared memory if you want cross-node context

## Review checklist
- queue a job
- confirm it appears in the orchestration overview
- verify mailbox items render in MailCenter
- verify runner-backed actions complete and update status
