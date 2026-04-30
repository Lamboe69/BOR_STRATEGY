# Limit Order Logic - TP Coverage Filter

## Overview

When a breakout candle closes beyond the signal level (S1 for buy, S4 for sell), the bot now checks how much of the TP distance has already been covered. If the candle has moved too far (> 20% of TP), the bot places a **LIMIT order** instead of entering immediately, waiting for a retrace back to the breakout level.

---

## Logic

### 1. Calculate TP Coverage

When a signal is detected:

```
Total TP Distance = |TP - Entry|

For BUY:  Distance Covered = Current Close - Entry
For SELL: Distance Covered = Entry - Current Close

TP Coverage % = (Distance Covered / Total TP Distance) × 100
```

### 2. Decision Tree

**If TP Coverage > 20%:**
- Place **LIMIT order** at the breakout level (S1 for buy, S4 for sell)
- SL and TP remain the same
- Wait for price to retrace back to entry level
- **Monitor price continuously**
- **If price reaches TP before retracing to entry → CANCEL the limit order**
- Order fills only if price returns to entry level BEFORE reaching TP

**If TP Coverage ≤ 20%:**
- Place **MARKET order** immediately (current behavior)
- Enter at current price
- SL and TP applied as usual

### 3. Limit Order Cancellation Logic

**For BUY limit orders:**
- Monitor current price every second
- If `current_price >= TP` → Cancel order (price went straight to TP)
- If `current_price <= entry` → Order fills (price retraced)

**For SELL limit orders:**
- Monitor current price every second
- If `current_price <= TP` → Cancel order (price went straight to TP)
- If `current_price >= entry` → Order fills (price retraced)

---

## Examples

### Example 1: BUY Signal - Immediate Entry

```
S1 = 1.1000 (breakout level)
S2 = 1.0990 (SL level)
TP = 1.1100 (10× SL distance)

Candle closes at 1.1015

Total TP Distance = 1.1100 - 1.1000 = 0.0100
Distance Covered  = 1.1015 - 1.1000 = 0.0015
TP Coverage       = (0.0015 / 0.0100) × 100 = 15%

✅ 15% ≤ 20% → MARKET order placed immediately
```

### Example 2: BUY Signal - Limit Order (Filled)

```
S1 = 1.1000 (breakout level)
S2 = 1.0990 (SL level)
TP = 1.1100 (10× SL distance)

Candle closes at 1.1030

Total TP Distance = 1.1100 - 1.1000 = 0.0100
Distance Covered  = 1.1030 - 1.1000 = 0.0030
TP Coverage       = (0.0030 / 0.0100) × 100 = 30%

❌ 30% > 20% → LIMIT order placed at 1.1000
   Price retraces to 1.0995 → Order fills at 1.1000 ✅
```

### Example 2b: BUY Signal - Limit Order (Cancelled)

```
S1 = 1.1000 (breakout level)
S2 = 1.0990 (SL level)
TP = 1.1100 (10× SL distance)

Candle closes at 1.1030

Total TP Distance = 1.1100 - 1.1000 = 0.0100
Distance Covered  = 1.1030 - 1.1000 = 0.0030
TP Coverage       = (0.0030 / 0.0100) × 100 = 30%

❌ 30% > 20% → LIMIT order placed at 1.1000
   Price continues to 1.1100 (TP) without retracing
   → Order CANCELLED ❌ (missed opportunity)
```

### Example 3: SELL Signal - Immediate Entry

```
S4 = 1.0950 (breakout level)
S3 = 1.0960 (SL level)
TP = 1.0850 (10× SL distance)

Candle closes at 1.0945

Total TP Distance = 1.0950 - 1.0850 = 0.0100
Distance Covered  = 1.0950 - 1.0945 = 0.0005
TP Coverage       = (0.0005 / 0.0100) × 100 = 5%

✅ 5% ≤ 20% → MARKET order placed immediately
```

### Example 4: SELL Signal - Limit Order (Filled)

```
S4 = 1.0950 (breakout level)
S3 = 1.0960 (SL level)
TP = 1.0850 (10× SL distance)

Candle closes at 1.0920

Total TP Distance = 1.0950 - 1.0850 = 0.0100
Distance Covered  = 1.0950 - 1.0920 = 0.0030
TP Coverage       = (0.0030 / 0.0100) × 100 = 30%

❌ 30% > 20% → LIMIT order placed at 1.0950
   Price retraces to 1.0955 → Order fills at 1.0950 ✅
```

### Example 4b: SELL Signal - Limit Order (Cancelled)

```
S4 = 1.0950 (breakout level)
S3 = 1.0960 (SL level)
TP = 1.0850 (10× SL distance)

Candle closes at 1.0920

Total TP Distance = 1.0950 - 1.0850 = 0.0100
Distance Covered  = 1.0950 - 1.0920 = 0.0030
TP Coverage       = (0.0030 / 0.0100) × 100 = 30%

❌ 30% > 20% → LIMIT order placed at 1.0950
   Price continues to 1.0850 (TP) without retracing
   → Order CANCELLED ❌ (missed opportunity)
```

### Example 5: Tokyo Limit Order - Cancelled by London Start

```
Tokyo session: 00:00-09:00 UTC
London session: 07:00-16:00 UTC

Tokyo BUY signal at 06:45 UTC
S1 = 1.1000, TP = 1.1100
Candle closes at 1.1030 (30% coverage)

→ LIMIT order placed at 1.1000

At 07:00 UTC: London session starts
→ Order CANCELLED ❌ (Tokyo levels invalid, London takes priority)
```

### Example 6: London Limit Order - Cancelled by Session End

```
London session: 07:00-16:00 UTC

London SELL signal at 15:30 UTC
S4 = 1.0950, TP = 1.0850
Candle closes at 1.0920 (30% coverage)

→ LIMIT order placed at 1.0950

Price stays at 1.0920 (no retrace, no TP hit)

At 16:00 UTC: London session ends
→ Order CANCELLED ❌ (session over, levels no longer valid)
```

---

## Benefits

1. **Avoids Late Entries**: Prevents entering trades that have already moved significantly
2. **Better Entry Price**: Waits for pullback to get optimal entry at breakout level
3. **Maintains R/R Ratio**: Full 1:10 risk/reward maintained when limit order fills
4. **Reduces Slippage**: Entry at exact breakout level instead of chasing price
5. **Smart Cancellation**: Automatically cancels orders when opportunity is missed (price reached TP)
6. **No Dead Orders**: Prevents limit orders from sitting indefinitely when price has moved away

---

## Backtest Simulation

In backtesting, when a limit order is placed:
- Bot checks the next 50 bars (12.5 hours on M15 timeframe)
- **Priority check 1**: Did session end? (Tokyo: London start OR Tokyo end; London: London end) → Cancel order, skip trade
- **Priority check 2**: Did price reach TP first? → Cancel order, skip trade
- **Secondary check**: Did price retrace to entry before above conditions? → Fill order, simulate trade
- If none happen → Order expires, skip trade
- Trade history shows `entry_type: "LIMIT"` or `"MARKET"` for tracking

---

## Live Trading

In live trading:
- Limit orders are placed with MT5 using `ORDER_TYPE_BUY_LIMIT` or `ORDER_TYPE_SELL_LIMIT`
- Bot monitors all pending limit orders every second (poll interval = 1s)
- **Automatic cancellation scenarios:**
  1. Price reaches TP without retracing → cancelled via `TRADE_ACTION_REMOVE`
  2. Tokyo orders: London session starts → cancelled (Tokyo levels invalid)
  3. Tokyo orders: Tokyo session ends → cancelled (session over)
  4. London orders: London session ends → cancelled (session over)
- **Automatic tracking**: If order fills (price retraced), it's moved to open positions tracking
- SL and TP are attached to the limit order
- Bot logs show TP coverage percentage, order type, and cancellation reasons

---

## Log Examples

**Market Order (≤ 20% coverage):**
```
MARKET order placed (TP coverage 15.0% ≤ 20%)  EURUSDm BUY  lot=0.10  entry=1.10000  SL=1.09900  TP=1.11000  R/R=1:10.0  ticket=12345
```

**Limit Order Placed (> 20% coverage):**
```
LIMIT order placed (TP coverage 30.0% > 20%)  EURUSDm BUY  lot=0.10  limit=1.10000  SL=1.09900  TP=1.11000  ticket=12346
Tracking pending limit order 12346 - will cancel if price reaches TP 1.11000
```

**Limit Order Filled (price retraced):**
```
Limit order 12346 filled at 1.10000 - now tracking as position
```

**Limit Order Cancelled (price reached TP):**
```
BUY limit order 12346 CANCELLED: price 1.11005 reached TP 1.11000 without retracing to entry 1.10000
```

**Limit Order Cancelled (Tokyo - London started):**
```
BUY limit order 12347 CANCELLED: London session started (Tokyo levels invalid)
```

**Limit Order Cancelled (session ended):**
```
SELL limit order 12348 CANCELLED: London session ended
```

---

## Configuration

No additional settings required. The 20% threshold is hardcoded in the logic.

To modify the threshold, edit `place_order()` in `live_bot.py`:
```python
if tp_coverage_pct > 20:  # Change 20 to desired percentage
```

---

## Testing Recommendations

1. **Monitor limit order fill rates** - track how often limit orders get filled vs skipped
2. **Compare performance** - backtest with/without this feature to measure impact
3. **Adjust threshold** - if too many trades are skipped, lower the 20% threshold
4. **Symbol-specific tuning** - volatile symbols may need different thresholds

---

## Risk Warning

- Limit orders may **never fill** if price doesn't retrace
- Limit orders will be **automatically cancelled** if price reaches TP first
- This could cause you to **miss profitable moves** that don't retrace
- Monitor fill rates and cancellation rates to assess effectiveness
- Consider market conditions (trending vs ranging)
- In strong trends, many limit orders may be cancelled as price moves straight to TP
- In ranging markets, limit orders are more likely to fill on retracements
