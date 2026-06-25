#!/bin/bash
cd /home/erick-lamboe/BOTMAN
/usr/bin/setsid /home/erick-lamboe/BOTMAN/venv/bin/python3 /home/erick-lamboe/BOTMAN/python_mt5/live_bot.py </dev/null >/dev/null 2>&1 &
PID=$!
echo "$PID" > /tmp/bot_pid.txt
disown "$PID"
echo "STARTED $PID"
