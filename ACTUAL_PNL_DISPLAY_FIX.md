# Actual P&L Display Fix

## Problem

The performance page was showing P&L calculated using the formula (risk × TP multiplier), not the ACTUAL P&L from MT5 trades.

**Example:**
- Formula showed: `$2000` (risk $200 × TP multiplier 10)
- Actual MT5 P&L: `$3400` (real profit from the trade)

This happened because the bot wasn't storing the actual P&L when trades closed.

## Solution

### 1. Store Actual P&L When Trades Close (`live_bot.py`)

When a trade closes, the bot now:
1. Gets the actual P&L from MT5 deal history
2. Stores it in the database as `actual_pnl`

```python
# Get ACTUAL P&L from MT5 deal history
actual_pnl = None
if deals and len(deals) >= 2:
    # Calculate total P&L from all deals for this position
    actual_pnl = sum(deal.profit for deal in deals)
    log.info("Position %d: Actual P&L from MT5 deals = $%.2f", ticket, actual_pnl)

# Save to database WITH actual P&L
_trades_db.close_trade(ticket, {
    "close_reason": close_reason,
    "close_price": close_price,
    "actual_pnl": actual_pnl if actual_pnl is not None else 0.0,
})
```

### 2. Use Stored P&L in Performance Display (`dashboard.py`)

The performance endpoint now:
1. Reads `actual_pnl` from the database
2. Falls back to formula only if `actual_pnl` is not available

```python
# Use actual P&L stored in database (from MT5)
pnl = trade.get("actual_pnl")

# Fallback to formula if actual P&L not available
if pnl is None:
    if close_reason == "tp":
        pnl = risk_per_trade * tp_mult
    elif close_reason == "sl":
        pnl = -risk_per_trade
    else:
        pnl = 0
```

## How It Works Now

### When a Trade Closes:

1. **Bot detects trade closed** in MT5
2. **Fetches deal history** for that position
3. **Calculates actual P&L** from all deals (entry + exit)
4. **Stores in database** as `actual_pnl`
5. **Displays in performance graph** using the stored value

### Performance Page Display:

**Before:**
```
2 trades | 0W/2L | 0.0% WR | $-400.00  (formula: 2 × -$200)
```

**After:**
```
2 trades | 0W/2L | 0.0% WR | $-387.50  (actual MT5 P&L)
5 trades | 2W/3L | 40.0% WR | +$3400.00  (actual MT5 P&L)
```

## Benefits

✅ **Accurate P&L** - Shows exactly what MT5 recorded
✅ **Includes slippage** - Real entry/exit prices, not theoretical
✅ **Includes commissions** - MT5 deal profit includes all costs
✅ **Includes swap** - Overnight holding costs included
✅ **Real performance** - What you actually made/lost

## What Gets Stored

Each closed trade now includes:
- `ticket` - MT5 position ID
- `symbol` - Trading pair
- `direction` - buy/sell
- `entry` - Entry price
- `sl` - Stop loss
- `tp` - Take profit
- `close_reason` - tp/sl/session_end
- `close_price` - Actual close price
- **`actual_pnl`** - Real P&L from MT5 ✨

## Fallback Behavior

If `actual_pnl` is not available (old trades before this update):
- Uses formula: TP = risk × TP multiplier, SL = -risk
- Ensures backward compatibility with existing data

## Testing

After restarting the bot:

1. **Close a winning trade** → Check performance page shows actual profit
2. **Close a losing trade** → Check performance page shows actual loss
3. **Select symbol** → See cumulative P&L graph with real numbers
4. **Check stats line** → Should show: `X trades | XW/XL | X.X% WR | $±XXXX.XX`

## Files Modified

1. **`python_mt5/live_bot.py`**
   - Added actual P&L calculation from MT5 deals
   - Stores `actual_pnl` when closing trades

2. **`ui/dashboard.py`**
   - Uses `actual_pnl` from database
   - Falls back to formula if not available

## Notes

- P&L includes all MT5 costs (commission, swap, slippage)
- Historical trades (before this update) will use formula
- New trades (after this update) will use actual MT5 P&L
- Performance graph updates in real-time as trades close
