# Limit Order and Trade Count Fix

## Problem Summary

XAUUSD placed 6 trades in one day when the maximum should be 2 per session:

1. **Tokyo limit order triggered during London session** - Should have been cancelled when London started
2. **3 additional trades during London session** - Exceeded the 2-trade limit
3. **Trade count included pending orders** - Count incremented when order placed, not when filled

## Root Causes

### Issue 1: Pending Orders Counted Before Filling
- Trade count was incremented IMMEDIATELY when order was placed
- If a limit order was placed but never filled (cancelled), the count stayed incremented
- This blocked new trades even though no actual trade occurred

### Issue 2: Limit Orders Not Properly Cancelled
- Tokyo limit orders could trigger during London session
- The cancellation logic existed but wasn't being enforced properly
- Orders should be cancelled when:
  - Tokyo session ends
  - London session starts (Tokyo levels become invalid)
  - Price reaches TP without retracing to entry

## Solution Implemented

### 1. Trade Count Logic Changed

**OLD BEHAVIOR:**
```
Place order → Increment count immediately → Track order
```

**NEW BEHAVIOR:**
```
Place MARKET order → Fills immediately → Increment count
Place LIMIT order → Track as pending → Increment count ONLY when filled
```

### 2. Database Changes (`trades_db.py`)

Added new methods:
- `decrement_trade_count(symbol, session)` - Decrement when order cancelled before filling
- `get_trade_count(symbol, session)` - Get current count directly

### 3. Live Bot Changes (`live_bot.py`)

#### When Signal is Generated:
```python
# Check current count from database
current_trade_count = _trades_db.get_trade_count(self.symbol, session)

if current_trade_count >= MAX_TRADES_PER_SESSION:
    log.warning("Signal ignored - session already has %d/%d trades")
    continue
```

#### When Market Order Fills:
```python
# Market order filled immediately - increment count NOW
_trades_db.increment_trade_count(self.symbol, session)
log.info("Market order filled - trade count: %d/%d")
```

#### When Limit Order Placed:
```python
# Pending order - DON'T increment count yet
self.pending_orders[ticket] = {
    "ticket": ticket,
    "session": session,
    "counted": False,  # Not counted yet
}
log.info("Pending limit order placed (not counted yet)")
```

#### When Limit Order Fills:
```python
# Order filled - increment count NOW
if not order_info.get("counted", False):
    _trades_db.increment_trade_count(self.symbol, order_session)
    log.info("Limit order filled - trade count: %d/%d")
```

#### When Limit Order Cancelled:
```python
# Order cancelled before filling - no need to decrement (never counted)
log.info("Limit order CANCELLED: %s", cancel_reason)
del self.pending_orders[ticket]
```

## Cancellation Rules for Limit Orders

### Tokyo Limit Orders:
- ✅ Cancelled when Tokyo session ends
- ✅ Cancelled when London session starts (Tokyo levels invalid)
- ✅ Cancelled if price reaches TP without retracing to entry

### London Limit Orders:
- ✅ Cancelled when London session ends
- ✅ Cancelled if price reaches TP without retracing to entry

## How It Works Now

### Scenario 1: Market Order (Price ≤ 20% to TP)
```
1. Signal detected at 08:00 Tokyo
2. Check: Tokyo trade_count = 0/2 ✓
3. Place MARKET order → Fills immediately
4. Increment count: Tokyo trade_count = 1/2
5. Track position
```

### Scenario 2: Limit Order (Price > 20% to TP)
```
1. Signal detected at 08:00 Tokyo
2. Check: Tokyo trade_count = 0/2 ✓
3. Place LIMIT order at entry level
4. DON'T increment count yet (pending)
5. Track as pending order

--- Later at 08:30 Tokyo ---
6. Limit order fills
7. Increment count: Tokyo trade_count = 1/2
8. Move to open positions
```

### Scenario 3: Limit Order Cancelled (London Starts)
```
1. Tokyo limit order placed at 08:45
2. Tokyo trade_count = 1/2 (from previous filled trade)
3. Pending order NOT counted yet

--- London opens at 09:00 ---
4. Detect London session start
5. Cancel Tokyo pending orders
6. Log: "CANCELLED: London session started"
7. Tokyo trade_count stays at 1/2 (order never filled)
8. London can now place up to 2 new trades
```

### Scenario 4: Limit Order Cancelled (TP Reached)
```
1. BUY limit order at 2650, TP at 2700
2. Price moves to 2705 without retracing to 2650
3. Cancel order: "price reached TP without retracing"
4. Order never filled, count not incremented
```

## Per-Symbol Trade Limits

Each symbol has **independent** limits:

| Symbol | Tokyo Max | London Max | Total Possible |
|--------|-----------|------------|----------------|
| EURUSD | 2         | 2          | 4              |
| XAUUSD | 2         | 2          | 4              |
| US30   | 2         | 2          | 4              |
| USTEC  | 2         | 2          | 4              |

**TOTAL ACROSS ALL SYMBOLS:** Up to 16 trades per day (4 symbols × 2 sessions × 2 trades)

## Log Messages to Monitor

### Normal Operation:
```
XAUUSD: New Tokyo session detected - trade_count reset to 0
XAUUSD: Market order filled immediately - trade count for TOKYO session: 1/2
XAUUSD: Pending limit order placed for TOKYO session (not counted yet)
XAUUSD: Limit order 12345 filled - trade count for TOKYO session: 2/2
```

### Limit Reached:
```
XAUUSD: Signal ignored - TOKYO session already has 2/2 trades
```

### Order Cancellations:
```
BUY limit order 12345 CANCELLED: London session started (Tokyo levels invalid)
BUY limit order 12346 CANCELLED: Tokyo session ended
SELL limit order 12347 CANCELLED: price 2705.50 reached TP 2700.00 without retracing
```

## Testing Checklist

- [ ] Place market order → Count increments immediately
- [ ] Place limit order → Count does NOT increment
- [ ] Limit order fills → Count increments when filled
- [ ] Limit order cancelled → Count stays same (never incremented)
- [ ] Tokyo limit order cancelled when London starts
- [ ] Limit order cancelled when session ends
- [ ] Limit order cancelled when TP reached without retrace
- [ ] Max 2 trades per symbol per session enforced
- [ ] Bot restart preserves trade counts correctly

## Key Improvements

1. ✅ **Accurate counting** - Only filled trades count toward limit
2. ✅ **Proper cancellation** - Tokyo orders cancelled when London starts
3. ✅ **Session isolation** - Tokyo and London limits are independent
4. ✅ **Per-symbol tracking** - Each pair has its own limits
5. ✅ **Survives restarts** - Counts persisted to database
6. ✅ **Clear logging** - Easy to track what's happening
