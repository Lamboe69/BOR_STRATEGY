# Session Trade Limit Fix

## Problem Identified

XAUUSD placed 6 trades in a single session when the maximum should be 2 per session.

### Root Cause

The `trade_count` for each session was **NOT being persisted** to the database. When the bot restarted:

1. ✅ `tokyo_wins` and `tokyo_losses` were restored from database
2. ❌ `tokyo.trade_count` and `london.trade_count` were NOT restored
3. ❌ Trade counts always started at 0 on every restart

**Result**: If the bot placed 2 trades, then restarted during the same session, it would allow 2 MORE trades because `trade_count` reset to 0.

## Solution Implemented

### 1. Database Changes (`trades_db.py`)

- Added `trade_count` field to `session_stats` structure
- Added `increment_trade_count(symbol, session)` method to increment count in database
- Added `reset_session_counts(symbol, session)` method to reset count when NEW session starts
- Modified `get_session_stats()` to return `trade_count`

### 2. Live Bot Changes (`live_bot.py`)

#### On Bot Startup:
```python
# Restore trade_count from database
bot.strategy.tokyo.trade_count = symbol_stats.get("tokyo", {}).get("trade_count", 0)
bot.strategy.london.trade_count = symbol_stats.get("london", {}).get("trade_count", 0)
```

#### On New Session Detection:
```python
# Reset trade_count in database when NEW session starts (not on every tick)
if tky_in and not self.strategy.tokyo.initialized:
    _trades_db.reset_session_counts(self.symbol, "tokyo")
```

#### Before Placing Order:
```python
# CRITICAL CHECK: Verify trade_count hasn't been exceeded
db_stats = _trades_db.get_session_stats(self.symbol)
current_trade_count = db_stats.get(session, {}).get("trade_count", 0)

if current_trade_count >= MAX_TRADES_PER_SESSION:
    log.warning("Signal ignored - session already has %d/%d trades", 
                current_trade_count, MAX_TRADES_PER_SESSION)
    continue
```

#### After Placing Order:
```python
# Increment trade_count in database IMMEDIATELY
_trades_db.increment_trade_count(self.symbol, session)
```

## How It Works Now

### Per-Symbol, Per-Session Limits

Each symbol has its own independent session limits:

- **EURUSD**: Max 2 Tokyo trades + Max 2 London trades
- **XAUUSD**: Max 2 Tokyo trades + Max 2 London trades
- **US30**: Max 2 Tokyo trades + Max 2 London trades
- **USTEC**: Max 2 Tokyo trades + Max 2 London trades

### Trade Count Lifecycle

1. **New Session Starts**: `trade_count` reset to 0 in database
2. **Signal Generated**: Check if `trade_count < MAX_TRADES_PER_SESSION`
3. **Order Placed**: Increment `trade_count` in database immediately
4. **Bot Restarts**: Restore `trade_count` from database (preserves count during session)
5. **Session Ends**: `trade_count` remains until next session starts

### Protection Against Exceeding Limits

- ✅ **Double-check before placing order**: Reads current count from database
- ✅ **Immediate increment**: Updates database right after order placement
- ✅ **Survives restarts**: Count persisted across bot restarts
- ✅ **Per-symbol tracking**: Each pair has independent limits
- ✅ **Session-aware**: Tokyo and London tracked separately

## Testing Recommendations

1. **Start bot during Tokyo session**
   - Verify it places max 2 trades for each symbol
   - Restart bot during session
   - Verify it doesn't place additional trades

2. **Monitor across session transition**
   - Verify Tokyo count resets when London starts
   - Verify London gets fresh 2-trade limit

3. **Check logs for warnings**
   - Look for "Signal ignored - session already has X/2 trades"
   - Verify trade count increments are logged

## Log Messages to Monitor

```
XAUUSD: New Tokyo session detected - trade_count reset to 0
XAUUSD: Trade count incremented for TOKYO session: 1/2
XAUUSD: Signal ignored - TOKYO session already has 2/2 trades
```
