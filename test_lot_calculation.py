"""
Test script to verify lot size calculations match exact risk percentage.

Run this to check if lot sizes for all symbols result in exactly the configured risk.
"""

import MetaTrader5 as mt5
import json
from pathlib import Path

# Load settings
SETTINGS_FILE = Path(__file__).parent / "bor_settings.json"
cfg = json.loads(SETTINGS_FILE.read_text())

MT5_LOGIN = int(cfg.get("mt5_login", 0))
MT5_PASSWORD = cfg.get("mt5_password", "")
MT5_SERVER = cfg.get("mt5_server", "")
MT5_PATH = cfg.get("mt5_path", "") or None
RISK_PCT = float(cfg.get("risk_pct", 1.0))
SYMBOLS = [s if isinstance(s, str) else s["name"] for s in cfg.get("symbols", [])]

# Connect to MT5
kwargs = {"login": MT5_LOGIN, "password": MT5_PASSWORD, "server": MT5_SERVER}
if MT5_PATH:
    kwargs["path"] = MT5_PATH

if not mt5.initialize(**kwargs):
    print(f"❌ MT5 init failed: {mt5.last_error()}")
    exit(1)

account_info = mt5.account_info()
balance = account_info.balance
risk_usd = balance * RISK_PCT / 100.0

print("=" * 90)
print(f"ACCOUNT: {account_info.login} | Balance: ${balance:.2f} | Risk: {RISK_PCT}% = ${risk_usd:.2f}")
print("=" * 90)
print()

def calc_lot_correct(symbol: str, entry: float, sl: float) -> float:
    """Correct lot calculation using MT5 tick values."""
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return 0.01
    
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        return sym_info.volume_min
    
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    ticks_in_sl = sl_distance / tick_size
    
    lot = risk_usd / (ticks_in_sl * tick_value)
    lot = round(lot / sym_info.volume_step) * sym_info.volume_step
    lot = max(sym_info.volume_min, min(sym_info.volume_max, lot))
    
    return lot

def verify_risk(symbol: str, lot: float, sl_distance: float) -> float:
    """Calculate actual risk in USD for given lot size and SL distance."""
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return 0.0
    
    tick_value = sym_info.trade_tick_value
    tick_size = sym_info.trade_tick_size
    ticks_in_sl = sl_distance / tick_size
    
    actual_risk = lot * ticks_in_sl * tick_value
    return actual_risk

# Test each symbol with realistic SL distances
test_cases = {
    "EURUSDm": {"entry": 1.08500, "sl": 1.08300},  # 20 pips
    "XAUUSDm": {"entry": 2650.00, "sl": 2645.00},  # $5
    "US30m": {"entry": 42500.0, "sl": 42450.0},    # 50 points
    "USTECm": {"entry": 20000.0, "sl": 19950.0},   # 50 points
    # Alternative symbol names (in case broker uses different format)
    "EURUSD": {"entry": 1.08500, "sl": 1.08300},
    "XAUUSD": {"entry": 2650.00, "sl": 2645.00},
    "GOLD": {"entry": 2650.00, "sl": 2645.00},
    "US30": {"entry": 42500.0, "sl": 42450.0},
    "US30.cash": {"entry": 42500.0, "sl": 42450.0},
    "DJ30": {"entry": 42500.0, "sl": 42450.0},
    "USTEC": {"entry": 20000.0, "sl": 19950.0},
    "NAS100": {"entry": 20000.0, "sl": 19950.0},
    "NAS100.cash": {"entry": 20000.0, "sl": 19950.0},
    "US100": {"entry": 20000.0, "sl": 19950.0},
}

print(f"{'Symbol':<15} {'Entry':<12} {'SL':<12} {'Distance':<12} {'Lot':<10} {'Risk $':<12} {'Error':<10}")
print("-" * 90)

for symbol in SYMBOLS:
    # Check if symbol exists in MT5
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        print(f"{symbol:<15} ❌ Symbol not found in MT5")
        continue
    
    # Get test case or use default values based on symbol type
    if symbol in test_cases:
        entry = test_cases[symbol]["entry"]
        sl = test_cases[symbol]["sl"]
    else:
        # Auto-generate test case based on current price
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            print(f"{symbol:<15} ❌ Cannot get tick data")
            continue
        
        current_price = (tick.ask + tick.bid) / 2
        
        # Determine SL distance based on symbol type
        symbol_upper = symbol.upper()
        if any(x in symbol_upper for x in ['XAU', 'GOLD']):
            sl_distance = 5.0  # $5 for gold
        elif any(x in symbol_upper for x in ['US30', 'DJ', 'DOW']):
            sl_distance = 50.0  # 50 points for Dow
        elif any(x in symbol_upper for x in ['NAS', 'USTEC', 'US100']):
            sl_distance = 50.0  # 50 points for Nasdaq
        elif any(x in symbol_upper for x in ['GBP', 'EUR', 'USD', 'JPY', 'AUD', 'CAD', 'CHF', 'NZD']):
            sl_distance = 0.00200  # 20 pips for forex
        else:
            # Default: 1% of current price
            sl_distance = current_price * 0.01
        
        entry = current_price
        sl = current_price - sl_distance
    sl_distance = abs(entry - sl)
    
    # Calculate lot
    lot = calc_lot_correct(symbol, entry, sl)
    
    # Verify actual risk
    actual_risk = verify_risk(symbol, lot, sl_distance)
    
    # Calculate error
    error_pct = ((actual_risk - risk_usd) / risk_usd * 100) if risk_usd > 0 else 0
    
    # Status indicator
    if abs(error_pct) < 1.0:
        status = "✅"
    elif abs(error_pct) < 5.0:
        status = "⚠️"
    else:
        status = "❌"
    
    print(f"{symbol:<15} {entry:<12.5f} {sl:<12.5f} {sl_distance:<12.5f} {lot:<10.2f} ${actual_risk:<11.2f} {error_pct:>+6.2f}% {status}")

print()
print("=" * 90)
print("Legend:")
print("  ✅ = Error < 1% (excellent)")
print("  ⚠️  = Error 1-5% (acceptable due to rounding)")
print("  ❌ = Error > 5% (needs investigation)")
print("=" * 90)

mt5.shutdown()
