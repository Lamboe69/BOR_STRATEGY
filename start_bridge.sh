#!/usr/bin/env bash
# start_bridge.sh — Start the mt5linux RPyC bridge server for MT5 under Wine.
#
# Usage:
#   ./start_bridge.sh               # start (or restart) the bridge server (foreground)
#   ./start_bridge.sh status        # check if bridge is running
#   ./start_bridge.sh stop          # stop the bridge server
#
# Bridge listens on 127.0.0.1:18812.
#
# For systemd, the service should use Type=simple (foreground mode).
# For manual background usage, run: nohup ./start_bridge.sh &

set -euo pipefail

BRIDGE_PORT=18812
BOTMAN_DIR="${BOTMAN_DIR:-$HOME/BOTMAN}"
LOG_FILE="${BOTMAN_DIR}/mt5linux_bridge.log"
PID_FILE="/tmp/mt5linux_bridge.pid"
WINE_PYTHON="$HOME/.wine/drive_c/users/erick-lamboe/AppData/Local/Programs/Python/Python312/python.exe"

cd "$BOTMAN_DIR"

status() {
    if ss -tlnp 2>/dev/null | grep -q "$BRIDGE_PORT"; then
        echo "Bridge RUNNING on port $BRIDGE_PORT"
        return 0
    fi
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Bridge running (PID $pid, not yet listening)"
            return 0
        fi
    fi
    echo "Bridge NOT running"
    return 1
}

stop() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        kill "$pid" 2>/dev/null && echo "Stopped bridge (PID $pid)" || true
        rm -f "$PID_FILE"
        return 0
    fi
    pids=$(pgrep -f "mt5linux.*$BRIDGE_PORT" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        kill $pids 2>/dev/null || true
        echo "Stopped bridge process(es)"
        return 0
    fi
    echo "Bridge not running"
    return 1
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

# Ensure correct numpy version (1.x, not 2.x) is installed
WINEDLLOVERRIDES="ucrtbase=n,b" wine "$WINE_PYTHON" -c "
import numpy
if numpy.__version__.startswith('1.'):
    print('numpy', numpy.__version__, 'OK')
else:
    print('ERROR: numpy', numpy.__version__, 'detected, need 1.x')
    exit(1)
" 2>/dev/null || {
    echo "Installing numpy 1.x (required for MT5)..."
    WINEDLLOVERRIDES="ucrtbase=n,b" wine "$WINE_PYTHON" -m pip install "numpy<2" 2>&1 | tail -3
}

echo "Starting mt5linux bridge server on port $BRIDGE_PORT..."
echo "Logs: $LOG_FILE"

export DISPLAY="${DISPLAY:-:0}"
WINEDLLOVERRIDES="ucrtbase=n,b" \
    nohup wine "$WINE_PYTHON" -c "
import os; os.chdir('C:/windows/temp')
import sys; sys.path = [p for p in sys.path if p != '']

# Inject numpy into RPyC SlaveService namespace before starting
import numpy as np
from rpyc.core.service import SlaveService

_orig_init = SlaveService.__init__
def _patched_init(self):
    _orig_init(self)
    self.namespace['np'] = np
    self.namespace['numpy'] = np
SlaveService.__init__ = _patched_init

exec(open('C:/users/erick-lamboe/AppData/Local/Programs/Python/Python312/Lib/site-packages/mt5linux/__main__.py').read())
" >> "$LOG_FILE" 2>&1 &

PID=$!
echo $PID > "$PID_FILE"

# Wait for bridge to be ready (fast check via RPyC)
BOTMAN_VENV_PYTHON="${BOTMAN_DIR}/venv/bin/python3"
for i in $(seq 1 60); do
    sleep 1
    if [ -f "$BOTMAN_VENV_PYTHON" ] && "$BOTMAN_VENV_PYTHON" -c "
import rpyc
try:
    c = rpyc.classic.connect('127.0.0.1', 18812); c.namespace and None; c.close()
    print('OK')
except: print('NO')
" 2>/dev/null | grep -q OK; then
        echo "Bridge ready (PID $PID)"
        exit 0
    fi
    if [ $((i % 15)) -eq 0 ]; then
        echo "Waiting for bridge... (${i}s)"
        tail -3 "$LOG_FILE"
    fi
done

echo "ERROR: Bridge failed to start within 60s. Check log: $LOG_FILE"
tail -20 "$LOG_FILE"
exit 1
