#!/usr/bin/env bash
set -euo pipefail

RUNNER_HOME="${RUNNER_HOME:-/opt/dashburg-runner}"
CRON_FILE="/etc/cron.d/dashburg-runner-mailbox"
CONFIG_PATH="${RUNNER_CONFIG_PATH:-/etc/dashburg-runner/config.yaml}"
LOG_FILE="/var/log/dashburg-runner-mailbox.log"

sudo install -d -m 755 /etc/cron.d
sudo touch "$LOG_FILE"
sudo chmod 644 "$LOG_FILE"

sudo tee "$CRON_FILE" >/dev/null <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# Dashburg mailbox worker schedules (bootstrap defaults; ScheduleOps UI can later override via /v1/schedules).
7 * * * * root $RUNNER_HOME/.venv/bin/python $RUNNER_HOME/scripts/mailbox_hourly_worker.py --config $CONFIG_PATH --recipient-kind runner >> $LOG_FILE 2>&1
11 * * * * root $RUNNER_HOME/.venv/bin/python $RUNNER_HOME/scripts/mailbox_hourly_worker.py --config $CONFIG_PATH --recipient-kind agent >> $LOG_FILE 2>&1
EOF

sudo chmod 644 "$CRON_FILE"
sudo systemctl reload cron >/dev/null 2>&1 || sudo service cron reload >/dev/null 2>&1 || true

echo "Installed mailbox worker cron at $CRON_FILE"
