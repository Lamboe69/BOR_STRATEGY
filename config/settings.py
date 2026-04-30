# BOR Strategy Configuration
import os
from pathlib import Path

# Load .env file manually (no python-dotenv needed)
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# MT5 connection  (values come from .env)
MT5_LOGIN    = int(os.environ.get("MT5_LOGIN",    "0"))
MT5_PASSWORD = os.environ.get("MT5_PASSWORD", "")
MT5_SERVER   = os.environ.get("MT5_SERVER",   "")
MT5_PATH     = os.environ.get("MT5_PATH",     "")

# Symbols to trade  (MT5 symbol names — adjust to match your broker)
SYMBOLS = ["EURUSD", "XAUUSD", "US30", "USTEC"]

# Risk per trade as a percentage of account balance
RISK_PCT = 1.0

# Max trades per session (Tokyo / London each)
MAX_TRADES_PER_SESSION = 2

# Sessions in UTC  (hour, minute)
TOKYO_START  = (0,  0)
TOKYO_END    = (9,  0)
LONDON_START = (7,  0)
LONDON_END   = (16, 0)

# 15-minute timeframe used for BOR level calculation
BOR_TIMEFRAME_MINUTES = 15

# TP multiplier  (10x the SL distance)
TP_MULTIPLIER = 10

# Live bot polling interval in seconds
POLL_INTERVAL = 10
