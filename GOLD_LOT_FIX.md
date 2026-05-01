# Gold (XAUUSD) Lot Size Fix

## Problem
Gold trades were only risking $14 instead of the configured risk percentage (e.g., 1% of $10,000 = $100).

## Root Cause
The commodity lot calculation formula was correct but the variable naming was confusing. Changed `point_val` to `value_per_unit` for clarity.

## How Gold Lot Calculation Works

### MT5 Gold Specifications (Typical)
- **Contract Size**: 100 oz
- **Tick Size**: 0.01 (smallest price movement)
- **Tick Value**: 0.01 USD (value of 1 tick)

### Formula
```
value_per_unit = (tick_value / tick_size) × contract_size
value_per_unit = (0.01 / 0.01) × 100 = 100

This means: $1 move in gold price = $100 per lot
```

### Example Calculation
```
Risk: 1% of $10,000 = $100
Entry: 2650.00
SL: 2645.00
SL Distance: 5.00

value_per_unit = 100 (as calculated above)
lot = risk_usd / (sl_distance × value_per_unit)
lot = 100 / (5.00 × 100)
lot = 100 / 500
lot = 0.20 lots

Verification:
0.20 lots × 5.00 points × $100 per point = $100 ✓
```

## Comparison with Other Instruments

### XAUUSD (Gold)
- Contract size: 100
- Tick size: 0.01
- Tick value: 0.01
- **Value per unit: 100** ($1 move = $100/lot)

### USTEC (Nasdaq 100)
- Contract size: 1
- Tick size: 0.01
- Tick value: 0.01
- **Value per unit: 1** (1 point move = $1/lot)

### EURUSD (Forex)
- Contract size: 100,000
- Uses pip calculation (different formula)
- 1 pip = $10 per lot

## Log Output
Now shows clearer variable names:
```
XAUUSD lot calc: risk=$100.00 sl_dist=5.00 tick_size=0.01000 tick_val=0.01000 contract_size=100 value_per_unit=100.00 → lot=0.20
```

## Testing
1. Check bot logs for gold trades
2. Verify `value_per_unit=100.00` for XAUUSD
3. Confirm lot size calculation: `lot = risk / (sl_distance × 100)`
4. Verify actual risk matches configured percentage
