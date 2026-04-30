# Per-Symbol Session Limits Implementation

## Overview
The bot now tracks session limits (max trades, wins/losses) **per-symbol individually**, not globally across all symbols.

## How It Works

### Example Scenario (max_trades_per_session = 2)

**Tokyo Session:**
- **EURUSDm**: Signal 1 → LOSS, Signal 2 → WIN → **STOP** (got win, no more EURUSDm trades this session)
- **XAUUSDm**: Signal 1 → LOSS, Signal 2 → LOSS → **STOP** (hit max 2 trades for XAUUSDm)
- **US30m**: Signal 1 → WIN → **STOP** (got win on first trade, no more US30m trades)
- **USTECm**: No signals yet → **CAN STILL TRADE** if signal appears

**Key Points:**
1. Each symbol has its own independent session counter
2. Max trades applies per-symbol, not globally
3. Once a symbol gets a WIN in that session → no more trades for that symbol
4. Continue taking trades (up to max) while losing
5. Other symbols are unaffected by one symbol's trades

## Files Changed

### 1. trades_db.py
**Changed:** Session stats structure from global to per-symbol

**Before:**
```json
{
  "session_stats": {
    "tokyo": {"wins": 5, "losses": 3},
    "london": {"wins": 8, "losses": 2}
  }
}
```

**After:**
```json
{
  "session_stats": {
    "EURUSDm": {
      "tokyo": {"wins": 2, "losses": 1},
      "london": {"wins": 3, "losses": 0}
    },
    "XAUUSDm": {
      "tokyo": {"wins": 1, "losses": 2},
      "london": {"wins": 2, "losses": 1}
    },
    "US30m": {
      "tokyo": {"wins": 1, "losses": 1},
      "london": {"wins": 2, "losses": 1}
    },
    "USTECm": {
      "tokyo": {"wins": 1, "losses": 0},
      "london": {"wins": 1, "losses": 2}
    }
  }
}
```

**Methods Updated:**
- `get_session_stats(symbol=None)` - Now accepts optional symbol parameter
- `close_trade()` - Updates per-symbol session stats
- `_load()` - Initializes empty per-symbol structure

### 2. live_bot.py
**Changed:** Load and restore per-symbol session stats on bot startup

**Before:**
```python
db_session_stats = _trades_db.get_session_stats()
for bot in bots:
    bot.strategy.tokyo_wins = db_session_stats.get("tokyo", {}).get("wins", 0)
    # ... same stats for all bots
```

**After:**
```python
for bot in bots:
    symbol_stats = _trades_db.get_session_stats(bot.symbol)
    bot.strategy.tokyo_wins = symbol_stats.get("tokyo", {}).get("wins", 0)
    bot.strategy.tokyo_losses = symbol_stats.get("tokyo", {}).get("losses", 0)
    # ... each bot gets its own symbol's stats
```

### 3. dashboard.py (Backtest)
**Changed:** Track per-symbol session stats during backtest

**Added:**
```python
# Per-symbol session tracking
symbol_session_stats = {
    "tokyo": {"wins": 0, "losses": 0, "trade_count": 0},
    "london": {"wins": 0, "losses": 0, "trade_count": 0}
}

# Update stats after each trade
if outcome == "tp":
    symbol_session_stats[session_name]["wins"] += 1
elif outcome == "sl":
    symbol_session_stats[session_name]["losses"] += 1
```

### 4. bor_logic.py
**No changes needed** - Already tracks session state per-strategy instance (one instance per symbol)

## Database Migration

The database version was updated from `1.0` to `2.0`.

**Automatic Migration:**
- Old databases with global session_stats will continue to work
- New trades will be tracked per-symbol
- Old global stats are ignored (fresh start per symbol)

**Manual Reset (if needed):**
```python
from trades_db import TradesDB
from pathlib import Path

db = TradesDB(Path("bor_trades.db.json"))
db.clear_all()  # Resets to new structure
```

## Testing

To verify per-symbol limits are working:

1. **Set max_trades_per_session = 2** in settings
2. **Start bot** with multiple symbols (e.g., EURUSDm, XAUUSDm, US30m, USTECm)
3. **Watch Tokyo session:**
   - EURUSDm takes 2 trades → should stop
   - XAUUSDm can still take 2 trades independently
   - US30m can still take 2 trades independently
   - USTECm can still take 2 trades independently
4. **Check database** `bor_trades.db.json`:
   - Should see separate stats for each symbol
5. **Restart bot:**
   - Each symbol should resume with its own session stats

## Benefits

✅ **Independent Symbol Trading**: One symbol hitting max trades doesn't block others  
✅ **Better Risk Distribution**: Can trade all 4 symbols simultaneously in same session  
✅ **Accurate Session Stats**: See which symbols perform best in Tokyo vs London  
✅ **Flexible Strategy**: Each symbol follows its own win/loss pattern  
✅ **Persistent Tracking**: Stats survive bot restarts per-symbol  

## Example Output

**Dashboard Session Stats (Tokyo Active):**
```
Tokyo Session (Active)
├─ EURUSDm:  2 trades (1W/1L) - STOPPED (hit max)
├─ XAUUSDm:  1 trade  (1W/0L) - STOPPED (got win)
├─ US30m:    2 trades (0W/2L) - STOPPED (hit max)
└─ USTECm:   0 trades (0W/0L) - CAN TRADE
```

**Database After Session:**
```json
{
  "session_stats": {
    "EURUSDm": {"tokyo": {"wins": 1, "losses": 1}},
    "XAUUSDm": {"tokyo": {"wins": 1, "losses": 0}},
    "US30m":   {"tokyo": {"wins": 0, "losses": 2}},
    "USTECm":  {"tokyo": {"wins": 0, "losses": 0}}
  }
}
```
