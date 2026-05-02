"""
backtest.py — BOR Strategy backtester (no broker required).

Data source: CSV files with columns: time, open, high, low, close, volume
             time format: YYYY-MM-DD HH:MM:SS  (UTC)

Usage:
    python python_backtest/backtest.py --csv data/EURUSD_M15.csv --symbol EURUSD

Or run without arguments to see a quick synthetic demo.
"""

import sys, csv, math, argparse, json
import datetime
import pytz
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bor_logic import BORStrategy, in_session

UTC = pytz.utc
ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "bor_settings.json"

# Load settings from bor_settings.json
def _load_settings():
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}

_cfg = _load_settings()
RISK_PCT = float(_cfg.get("risk_pct", 1.0))
MAX_TRADES_PER_SESSION = int(_cfg.get("max_trades_per_session", 2))
TP_MULTIPLIER = float(_cfg.get("tp_multiplier", 10))

# Parse session times from settings (broker time → UTC)
def _parse_time(t: str) -> tuple:
    h, m = t.split(":")
    return int(h), int(m)

def _broker_to_utc(t: tuple, offset_h: int) -> tuple:
    total = t[0] * 60 + t[1] - offset_h * 60
    total %= 1440
    return total // 60, total % 60

TZ_OFFSET = int(_cfg.get("timezone_offset", 0))
_ses = _cfg.get("sessions", {})
_tky = _ses.get("tokyo",  {"start": "00:00", "end": "09:00"})
_ldn = _ses.get("london", {"start": "07:00", "end": "16:00"})

TOKYO_START  = _broker_to_utc(_parse_time(_tky.get("start", "00:00")), TZ_OFFSET)
TOKYO_END    = _broker_to_utc(_parse_time(_tky.get("end",   "09:00")), TZ_OFFSET)
LONDON_START = _broker_to_utc(_parse_time(_ldn.get("start", "07:00")), TZ_OFFSET)
LONDON_END   = _broker_to_utc(_parse_time(_ldn.get("end",   "16:00")), TZ_OFFSET)


# ── CSV loader ────────────────────────────────────────────────────────────────

def load_csv(path: str) -> list:
    bars = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            bars.append({
                "time":  datetime.datetime.strptime(
                             row["time"], "%Y-%m-%d %H:%M:%S"
                         ).replace(tzinfo=UTC),
                "open":  float(row["open"]),
                "high":  float(row["high"]),
                "low":   float(row["low"]),
                "close": float(row["close"]),
            })
    return bars


# ── backtest engine ───────────────────────────────────────────────────────────

def run_backtest(bars: list, symbol: str, initial_balance: float = 10_000.0):
    balance = initial_balance

    def get_balance():
        return balance

    strategy = BORStrategy(
        symbol=symbol,
        risk_pct=RISK_PCT,
        account_balance_fn=get_balance,
        max_trades=MAX_TRADES_PER_SESSION,
        tp_mult=TP_MULTIPLIER,
        tokyo_start=TOKYO_START,   tokyo_end=TOKYO_END,
        london_start=LONDON_START, london_end=LONDON_END,
    )

    trades = []

    for i in range(1, len(bars)):
        bar  = bars[i]
        prev = bars[i - 1]

        signals = strategy.on_candle(
            utc_dt=bar["time"],
            high=bar["high"], low=bar["low"],
            close=bar["close"], prev_close=prev["close"],
            pre_h=prev["high"], pre_l=prev["low"],
            open_h=bar["high"], open_l=bar["low"],
        )

        for sig in signals:
            risk_usd = balance * RISK_PCT / 100.0
            sl_dist  = abs(sig["entry"] - sig["sl"])

            # Simulate outcome by scanning forward bars
            outcome, close_price, close_time = _simulate_trade(
                bars, i, sig["direction"], sig["tp"], sig["sl"]
            )

            pnl = risk_usd * TP_MULTIPLIER if outcome == "tp" else -risk_usd
            balance += pnl

            trades.append({
                "time":      sig["time"].strftime("%Y-%m-%d %H:%M"),
                "session":   sig["session"],
                "direction": sig["direction"],
                "entry":     round(sig["entry"], 5),
                "sl":        round(sig["sl"],    5),
                "tp":        round(sig["tp"],    5),
                "outcome":   outcome,
                "pnl":       round(pnl, 2),
                "balance":   round(balance, 2),
                "close_time": close_time.strftime("%Y-%m-%d %H:%M") if close_time else "",
            })

    return trades, balance


def _simulate_trade(bars, entry_idx, direction, tp, sl):
    """Scan forward from entry_idx to find first TP or SL hit."""
    for j in range(entry_idx + 1, len(bars)):
        b = bars[j]
        if direction == "buy":
            if b["high"] >= tp:
                return "tp", tp, b["time"]
            if b["low"]  <= sl:
                return "sl", sl, b["time"]
        else:
            if b["low"]  <= tp:
                return "tp", tp, b["time"]
            if b["high"] >= sl:
                return "sl", sl, b["time"]
    return "open", bars[-1]["close"], bars[-1]["time"]


# ── report ────────────────────────────────────────────────────────────────────

def print_report(trades: list, initial: float, final: float, symbol: str):
    wins   = sum(1 for t in trades if t["outcome"] == "tp")
    losses = sum(1 for t in trades if t["outcome"] == "sl")
    total  = wins + losses
    wr     = wins / total * 100 if total else 0
    net    = final - initial

    print(f"\n{'-'*55}")
    print(f"  BOR Backtest Report - {symbol}")
    print(f"{'-'*55}")
    print(f"  Total trades : {total}")
    print(f"  Wins         : {wins}")
    print(f"  Losses       : {losses}")
    print(f"  Win rate     : {wr:.1f}%")
    print(f"  Initial bal  : ${initial:,.2f}")
    print(f"  Final bal    : ${final:,.2f}")
    print(f"  Net P&L      : ${net:+,.2f}  ({net/initial*100:+.1f}%)")
    print(f"{'-'*55}\n")

    # Per-session breakdown
    for ses in ("tokyo", "london"):
        st = [t for t in trades if t["session"] == ses]
        sw = sum(1 for t in st if t["outcome"] == "tp")
        sl = sum(1 for t in st if t["outcome"] == "sl")
        sp = sum(t["pnl"] for t in st)
        print(f"  {ses.capitalize():8s}  W:{sw}  L:{sl}  P&L:${sp:+,.2f}")
    print()

    # Last 20 trades
    print(f"  {'Time':<17} {'Ses':<7} {'Dir':<5} {'Entry':>9} {'SL':>9} {'TP':>9} {'Out':<4} {'P&L':>8} {'Bal':>10}")
    print(f"  {'-'*17} {'-'*7} {'-'*5} {'-'*9} {'-'*9} {'-'*9} {'-'*4} {'-'*8} {'-'*10}")
    for t in trades[-20:]:
        print(f"  {t['time']:<17} {t['session']:<7} {t['direction']:<5} "
              f"{t['entry']:>9.5f} {t['sl']:>9.5f} {t['tp']:>9.5f} "
              f"{t['outcome']:<4} {t['pnl']:>8.2f} {t['balance']:>10.2f}")


# ── synthetic demo data ───────────────────────────────────────────────────────

def _make_demo_bars():
    """Generate 30 days of synthetic 15-min EURUSD-like bars for demo."""
    import random
    random.seed(42)
    bars = []
    price = 1.08500
    start = datetime.datetime(2024, 1, 2, 0, 0, tzinfo=UTC)
    for i in range(30 * 24 * 4):   # 30 days × 96 bars/day
        dt = start + datetime.timedelta(minutes=15 * i)
        o  = price
        c  = o + random.gauss(0, 0.0003)
        h  = max(o, c) + abs(random.gauss(0, 0.0002))
        l  = min(o, c) - abs(random.gauss(0, 0.0002))
        bars.append({"time": dt, "open": o, "high": h, "low": l, "close": c})
        price = c
    return bars


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="BOR Strategy Backtester")
    parser.add_argument("--csv",     default="",        help="Path to 15-min CSV file")
    parser.add_argument("--symbol",  default="EURUSD",  help="Symbol name")
    parser.add_argument("--balance", default=10000.0,   type=float, help="Starting balance")
    args = parser.parse_args()

    if args.csv:
        print(f"Loading {args.csv}…")
        bars = load_csv(args.csv)
    else:
        print("No CSV provided — running synthetic demo…")
        bars = _make_demo_bars()

    print(f"Bars loaded: {len(bars)}")
    trades, final_balance = run_backtest(bars, args.symbol, args.balance)
    print_report(trades, args.balance, final_balance, args.symbol)


if __name__ == "__main__":
    main()
