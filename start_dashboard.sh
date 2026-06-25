#!/usr/bin/env bash
# start_dashboard.sh — Start the BOR Strategy Flask dashboard.
# Stops any existing instance first, then starts fresh.
#
# The mt5linux bridge must be running first (start_bridge.sh).
#
# Usage:
#   ./start_dashboard.sh            # start
#   ./start_dashboard.sh stop       # stop
#   ./start_dashboard.sh restart    # restart
#   ./start_dashboard.sh status     # check

set -euo pipefail

BOTMAN_DIR="${BOTMAN_DIR:-$HOME/BOTMAN}"
cd "$BOTMAN_DIR"

DASHBOARD_PORT=5000
PID_FILE="/tmp/dashboard.pid"
LOG_FILE="$BOTMAN_DIR/dashboard.log"

VENV_PYTHON="$BOTMAN_DIR/venv/bin/python"
DASHBOARD_SCRIPT="$BOTMAN_DIR/ui/dashboard.py"

status() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Dashboard running (PID $pid) on port $DASHBOARD_PORT"
            return 0
        fi
        rm -f "$PID_FILE"
    fi
    echo "Dashboard NOT running"
    return 1
}

stop() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        kill "$pid" 2>/dev/null && echo "Stopped dashboard (PID $pid)" || true
        rm -f "$PID_FILE"
    fi
}

case "${1:-start}" in
    status)
        status
        exit $?
        ;;
    stop)
        stop
        exit 0
        ;;
    start|restart)
        stop
        ;;
esac

echo "Starting dashboard on port $DASHBOARD_PORT..."

source "$BOTMAN_DIR/venv/bin/activate"
nohup "$VENV_PYTHON" "$DASHBOARD_SCRIPT" > "$LOG_FILE" 2>&1 &
PID=$!
echo $PID > "$PID_FILE"

for i in $(seq 1 10); do
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
        echo "Dashboard started (PID $PID) — http://localhost:$DASHBOARD_PORT"
        exit 0
    fi
done

echo "ERROR: Dashboard failed to start. Check log: $LOG_FILE"
tail -10 "$LOG_FILE"
exit 1
