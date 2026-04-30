# BOR Strategy Trading Bot

Implements the **Break-of-Range (BOR)** strategy from the LuxAlgo BOR Strategy
indicator in Python — both a **live MT5 bot** and a **CSV backtester**.

---

## Strategy Logic

At each **Tokyo** (00:00–09:00 UTC) and **London** (07:00–16:00 UTC) session open:

1. Snapshot 4 price levels from the 15-min chart:
   - `pre_high` / `pre_low`   — last closed 15-min candle **before** the session
   - `open_high` / `open_low` — first 15-min candle **of** the session

2. Sort them high → low: **S1 > S2 > S3 > S4**

3. **Buy signal** — close crosses above S1  
   - Entry = S1 · SL = S2 · TP = Entry + (Entry − SL) × 10

4. **Sell signal** — close crosses below S4  
   - Entry = S4 · SL = S3 · TP = Entry − (SL − Entry) × 10

5. **Session rules**
   - Max 2 trades per session (configurable)
   - Stop all signals once a **win** is recorded in that session
   - **Wick-out filter**: if the previous loss was a wick (SL wick but body
     did NOT close beyond SL), the next same-direction signal requires the
     breakout candle to **close** beyond the previous entry price

---

## Project Structure

```
BOR_Bot/
├── bor_logic.py              ← core strategy engine (shared)
├── requirements.txt
├── config/
│   └── settings.py           ← all configuration lives here
├── python_mt5/
│   └── live_bot.py           ← live trading via MetaTrader 5 API
└── python_backtest/
    └── backtest.py           ← CSV backtester / demo mode
```

---

## Quick Start

### 1 — Install dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `MetaTrader5` only installs on Windows. The backtester works on
> any OS without it.

### 2 — Configure

Edit `config/settings.py`:

```python
MT5_LOGIN    = 123456        # your account number
MT5_PASSWORD = "your_pass"
MT5_SERVER   = "BrokerName-Live"

SYMBOLS  = ["EURUSD", "XAUUSD", "US30.cash", "NAS100.cash"]
RISK_PCT = 1.0               # 1 % of balance per trade
```

> Symbol names must match exactly what your broker uses in MT5.
> Common alternatives: `GOLD`, `XAUUSD`, `US30`, `DJ30`, `NAS100`, `USTEC`.

### 3a — Run the live bot

```bash
cd BOR_Bot
python python_mt5/live_bot.py
```

The bot polls every 10 seconds, detects new closed 15-min bars, and places
market orders with SL/TP automatically.

### 3b — Run the backtester

**With your own CSV data:**

```bash
python python_backtest/backtest.py --csv path/to/EURUSD_M15.csv --symbol EURUSD --balance 10000
```

CSV format (header required):

```
time,open,high,low,close,volume
2024-01-02 00:00:00,1.10500,1.10520,1.10480,1.10510,1234
...
```

**Quick synthetic demo (no data needed):**

```bash
python python_backtest/backtest.py
```

---

## Symbols & Broker Notes

| Instrument | Typical MT5 name | Alternatives |
|------------|-----------------|--------------|
| EUR/USD    | `EURUSD`        | —            |
| Gold       | `XAUUSD`        | `GOLD`       |
| Dow Jones  | `US30.cash`     | `US30`, `DJ30` |
| Nasdaq 100 | `NAS100.cash`   | `NAS100`, `USTEC` |

---

## Risk Warning

This software is for **educational purposes only**.  
Trading financial instruments involves substantial risk of loss.  
Always test on a **demo account** before going live.
