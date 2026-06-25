#!/usr/bin/env bash
cd /home/erick-lamboe/BOTMAN
nohup ./venv/bin/python3 python_mt5/live_bot.py >> /tmp/live_bot.log 2>&1 &
echo $!
