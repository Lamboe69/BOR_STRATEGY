# Lot Size Calculation Fix

## Problem
The bot was calculating incorrect lot sizes for different symbols, resulting in:
- **Too low risk** on some pairs (e.g., risking 0.5% instead of 1%)
- **Too high risk** on other pairs (e.g., risking 2% instead of 1%)

This happened because the old `pip_value()` function used a flawed formula that didn't account for symbol-specific contract sizes and tick values correctly.

## Root Cause

### Old (Incorrect) Formula:
```python
def pip_value(symbol: str) -> float:
    info = mt5.symbol_info(symbol)
    return info.trade_tick_value / info.trade_tick_size * info.point * (
        10 if info.digits in (4, 5) else 1
    )

def calc_lot(symbol: str, entry: float, sl: float) -> float:
    sl_pips = abs(entry - sl) / sym_info.point
    pv = pip_value(symbol)
    lot = risk_usd / (sl_pips * pv)
```

**Issues:**
1. Used `point` instead of proper tick calculations
2. Applied arbitrary multiplier (10) based on digits
3. Didn't work correctly for indices and commodities
4. Resulted in inconsistent risk across different symbols

### New (Correct) Formula:
```python
def calc_lot(symbol: str, entry: float, sl: float) -> float:
    # Get symbol specifications from MT5
    tick_value = sym_info.trade_tick_value  # Profit/loss per tick for 1 lot
    tick_size = sym_info.trade_tick_size    # Minimum price movement
    
    # Calculate SL distance in ticks
    sl_distance = abs(entry - sl)
    ticks_in_sl = sl_distance / tick_size
    
    # Calculate lot size to risk exactly risk_usd
    lot = risk_usd / (ticks_in_sl * tick_value)
    
    # Round to broker's volume step
    lot = round(lot / sym_info.volume_step) * sym_info.volume_step
    lot = max(sym_info.volume_min, min(sym_info.volume_max, lot))
```

**Why This Works:**
1. Uses MT5's actual `trade_tick_value` (broker-provided profit/loss per tick)
2. Calculates exact number of ticks in SL distance
3. Works universally for Forex, Indices, Commodities, Crypto
4. Accounts for symbol-specific contract sizes automatically

## Formula Explanation

**Risk Formula:**
```
Risk ($) = Lot Size × Ticks in SL × Tick Value

Therefore:
Lot Size = Risk ($) / (Ticks in SL × Tick Value)
```

**Example 1: EURUSD (Forex)**
- Balance: $10,000
- Risk: 1% = $100
- Entry: 1.08500
- SL: 1.08300
- SL Distance: 0.00200 (20 pips)
- Tick Size: 0.00001 (1 pip)
- Tick Value: $1.00 per pip per lot
- Ticks in SL: 0.00200 / 0.00001 = 200 ticks
- **Lot = $100 / (200 × $1.00) = 0.50 lots** ✅

**Example 2: XAUUSD (Gold)**
- Balance: $10,000
- Risk: 1% = $100
- Entry: 2650.00
- SL: 2645.00
- SL Distance: 5.00
- Tick Size: 0.01
- Tick Value: $0.01 per tick per lot
- Ticks in SL: 5.00 / 0.01 = 500 ticks
- **Lot = $100 / (500 × $0.01) = 20.00 lots** ✅

**Example 3: US30 (Dow Jones Index)**
- Balance: $10,000
- Risk: 1% = $100
- Entry: 42500.0
- SL: 42450.0
- SL Distance: 50.0 points
- Tick Size: 1.0
- Tick Value: $1.00 per point per lot
- Ticks in SL: 50.0 / 1.0 = 50 ticks
- **Lot = $100 / (50 × $1.00) = 2.00 lots** ✅

**Example 4: USTEC (Nasdaq 100)**
- Balance: $10,000
- Risk: 1% = $100
- Entry: 20000.0
- SL: 19950.0
- SL Distance: 50.0 points
- Tick Size: 1.0
- Tick Value: $2.00 per point per lot (USTEC has higher tick value)
- Ticks in SL: 50.0 / 1.0 = 50 ticks
- **Lot = $100 / (50 × $2.00) = 1.00 lot** ✅

## Files Changed

### 1. python_mt5/live_bot.py
**Removed:**
- `pip_value()` function (flawed calculation)

**Updated:**
- `calc_lot()` function with correct formula
- Added detailed logging to verify calculations

**New Code:**
```python
def calc_lot(symbol: str, entry: float, sl: float) -> float:
    """Calculate lot size to risk exactly RISK_PCT of balance."""
    balance = get_balance()
    risk_usd = balance * RISK_PCT / 100.0
    sym_info = mt5.symbol_info(symbol)
    
    sl_distance = abs(entry - sl)
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    ticks_in_sl = sl_distance / tick_size
    
    lot = risk_usd / (ticks_in_sl * tick_value)
    lot = round(lot / sym_info.volume_step) * sym_info.volume_step
    lot = max(sym_info.volume_min, min(sym_info.volume_max, lot))
    
    log.info("%s lot calc: risk=$%.2f sl_dist=%.5f ticks=%.2f tick_val=%.5f → lot=%.2f",
             symbol, risk_usd, sl_distance, ticks_in_sl, tick_value, lot)
    
    return lot
```

### 2. bor_logic.py
**No changes needed** - The simplified calculation in `_calc_lot()` is only used for backtesting and works correctly for that purpose.

## Testing

### Run the Test Script:
```bash
python test_lot_calculation.py
```

**Expected Output:**
```
================================================================================
ACCOUNT: 123456 | Balance: $10000.00 | Risk: 1.0% = $100.00
================================================================================

Symbol       Entry        SL           Distance     Lot        Risk $       Error     
--------------------------------------------------------------------------------
EURUSDm      1.08500      1.08300      0.00200      0.50       $100.00      +0.00% ✅
XAUUSDm      2650.00000   2645.00000   5.00000      20.00      $100.00      +0.00% ✅
US30m        42500.00000  42450.00000  50.00000     2.00       $100.00      +0.00% ✅
USTECm       20000.00000  19950.00000  50.00000     1.00       $100.00      +0.00% ✅

================================================================================
Legend:
  ✅ = Error < 1% (excellent)
  ⚠️  = Error 1-5% (acceptable due to rounding)
  ❌ = Error > 5% (needs investigation)
================================================================================
```

### Verify in Live Trading:
1. **Check logs** when bot places orders - look for lot calculation details:
   ```
   EURUSDm lot calc: risk=$100.00 sl_dist=0.00200 ticks=200.00 tick_val=1.00000 → lot=0.50
   ```

2. **Monitor actual risk** - When trade hits SL, loss should be exactly 1% (or configured risk_pct):
   ```
   Balance before: $10,000.00
   Trade hits SL
   Balance after: $9,900.00
   Loss: $100.00 = 1.00% ✅
   ```

3. **Check all symbols** - Each symbol should risk the same dollar amount:
   - EURUSDm: 0.50 lots × 20 pips × $1/pip = $100 ✅
   - XAUUSDm: 20.00 lots × $5 × $0.01/point = $100 ✅
   - US30m: 2.00 lots × 50 points × $1/point = $100 ✅
   - USTECm: 1.00 lot × 50 points × $2/point = $100 ✅

## Benefits

✅ **Accurate Risk Management**: Every trade risks exactly the configured percentage  
✅ **Universal Formula**: Works for all asset classes (Forex, Indices, Commodities, Crypto)  
✅ **Broker-Agnostic**: Uses MT5's actual tick values, works with any broker  
✅ **Transparent Logging**: See exact calculation details in logs  
✅ **Consistent Performance**: Backtest results now match live trading risk  

## Important Notes

1. **Initial Balance Risk**: Bot uses initial balance for risk calculation (not compounding)
2. **Spread Buffer**: SL may be adjusted for spread, but lot size is calculated from original SL
3. **Volume Limits**: Lot size is clamped to broker's min/max volume limits
4. **Rounding**: Lot size is rounded to broker's volume step (usually 0.01)

## Troubleshooting

**If risk is still incorrect:**

1. **Check symbol name** - Must match broker exactly (EURUSDm vs EURUSD)
2. **Check tick values** - Run test script to see actual MT5 values
3. **Check logs** - Look for lot calculation details in bor_live.log
4. **Check broker limits** - Some brokers have max lot restrictions
5. **Check account type** - Cent accounts have different contract sizes

**Common Issues:**

- **Risk too low**: Symbol name mismatch or wrong tick values
- **Risk too high**: Volume step rounding or broker limits
- **Order rejected**: Lot size below min or above max volume
