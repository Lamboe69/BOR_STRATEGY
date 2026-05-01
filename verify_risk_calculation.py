"""
Risk Calculation Verification for XAUUSD and US30
Run this script to verify lot size calculations are accurate
"""

import MetaTrader5 as mt5
import json
from pathlib import Path

# Load settings
SETTINGS_FILE = Path(__file__).parent / "bor_settings.json"
cfg = json.loads(SETTINGS_FILE.read_text())
INITIAL_BALANCE = float(cfg.get("initial_balance", 10000))
RISK_PCT = float(cfg.get("risk_pct", 1.0))

# Connect to MT5
MT5_LOGIN = int(cfg.get("mt5_login", 0))
MT5_PASSWORD = str(cfg.get("mt5_password", ""))
MT5_SERVER = str(cfg.get("mt5_server", ""))
MT5_PATH = str(cfg.get("mt5_path", ""))

kwargs = dict(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
if MT5_PATH:
    kwargs["path"] = MT5_PATH

if not mt5.initialize(**kwargs):
    print(f"MT5 init failed: {mt5.last_error()}")
    exit(1)

print(f"Connected to MT5 - Account: {MT5_LOGIN}")
print(f"Initial Balance: ${INITIAL_BALANCE:,.2f}")
print(f"Risk Per Trade: {RISK_PCT}% = ${INITIAL_BALANCE * RISK_PCT / 100:.2f}")
print("=" * 80)

def verify_symbol(symbol: str, test_entry: float, test_sl: float):
    """Verify lot calculation for a symbol with test values"""
    
    print(f"\n{'='*80}")
    print(f"SYMBOL: {symbol}")
    print(f"{'='*80}")
    
    # Get symbol info
    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        print(f"ERROR: Symbol {symbol} not found in MT5")
        return
    
    # Display MT5 specifications
    print(f"\nMT5 SPECIFICATIONS:")
    print(f"   Contract Size:    {sym_info.trade_contract_size:,.0f}")
    print(f"   Tick Size:        {sym_info.trade_tick_size}")
    print(f"   Tick Value:       ${sym_info.trade_tick_value}")
    print(f"   Digits:           {sym_info.digits}")
    print(f"   Min Lot:          {sym_info.volume_min}")
    print(f"   Max Lot:          {sym_info.volume_max}")
    print(f"   Lot Step:         {sym_info.volume_step}")
    
    # Calculate risk
    risk_usd = INITIAL_BALANCE * RISK_PCT / 100.0
    sl_distance = abs(test_entry - test_sl)
    
    print(f"\nTEST SCENARIO:")
    print(f"   Entry Price:      {test_entry}")
    print(f"   Stop Loss:        {test_sl}")
    print(f"   SL Distance:      {sl_distance}")
    print(f"   Risk Amount:      ${risk_usd:.2f}")
    
    # Calculate value per unit
    tick_size = sym_info.trade_tick_size
    tick_value = sym_info.trade_tick_value
    contract_size = sym_info.trade_contract_size
    
    # CRITICAL: tick_value already includes contract_size effect
    # Just divide tick_value by tick_size to get value per 1.0 unit
    if tick_size > 0:
        value_per_unit = tick_value / tick_size
    else:
        value_per_unit = tick_value
    
    print(f"\nCALCULATION:")
    print(f"   value_per_unit = tick_value / tick_size")
    print(f"   value_per_unit = {tick_value} / {tick_size}")
    print(f"   value_per_unit = {value_per_unit:.2f}")
    print(f"   ")
    print(f"   Meaning: 1.0 price unit move = ${value_per_unit:.2f} per lot")
    
    # Calculate lot size
    lot_raw = risk_usd / (sl_distance * value_per_unit)
    lot_rounded = round(lot_raw / sym_info.volume_step) * sym_info.volume_step
    lot_final = max(sym_info.volume_min, min(sym_info.volume_max, lot_rounded))
    
    print(f"\nLOT SIZE CALCULATION:")
    print(f"   lot = risk_usd / (sl_distance × value_per_unit)")
    print(f"   lot = {risk_usd:.2f} / ({sl_distance} × {value_per_unit:.2f})")
    print(f"   lot = {risk_usd:.2f} / {sl_distance * value_per_unit:.2f}")
    print(f"   lot = {lot_raw:.6f} (raw)")
    print(f"   lot = {lot_rounded:.2f} (rounded to step {sym_info.volume_step})")
    print(f"   lot = {lot_final:.2f} (final, clamped to min/max)")
    
    # Verify actual risk
    actual_risk = lot_final * sl_distance * value_per_unit
    risk_error = abs(actual_risk - risk_usd)
    risk_error_pct = (risk_error / risk_usd * 100) if risk_usd > 0 else 0
    
    print(f"\nVERIFICATION:")
    print(f"   Actual Risk = lot × sl_distance × value_per_unit")
    print(f"   Actual Risk = {lot_final:.2f} × {sl_distance} × {value_per_unit:.2f}")
    print(f"   Actual Risk = ${actual_risk:.2f}")
    print(f"   Target Risk = ${risk_usd:.2f}")
    print(f"   Difference  = ${risk_error:.2f} ({risk_error_pct:.2f}%)")
    
    if risk_error_pct < 5:
        print(f"   PASS - Risk calculation is accurate!")
    else:
        print(f"   WARNING - Risk error is {risk_error_pct:.2f}%")
    
    # Show what happens with different SL distances
    print(f"\nLOT SIZE TABLE (for different SL distances):")
    print(f"   {'SL Distance':<15} {'Lot Size':<12} {'Actual Risk':<15} {'Error':<10}")
    print(f"   {'-'*15} {'-'*12} {'-'*15} {'-'*10}")
    
    for sl_test in [1, 2, 5, 10, 20, 50]:
        lot_test = risk_usd / (sl_test * value_per_unit)
        lot_test = round(lot_test / sym_info.volume_step) * sym_info.volume_step
        lot_test = max(sym_info.volume_min, min(sym_info.volume_max, lot_test))
        risk_test = lot_test * sl_test * value_per_unit
        error_test = abs(risk_test - risk_usd)
        print(f"   {sl_test:<15} {lot_test:<12.2f} ${risk_test:<14.2f} ${error_test:<9.2f}")

# Test XAUUSD (Gold)
verify_symbol("XAUUSDm", test_entry=2650.00, test_sl=2645.00)

# Test US30 (Dow Jones)
verify_symbol("US30m", test_entry=42000.0, test_sl=41950.0)

print(f"\n{'='*80}")
print("VERIFICATION COMPLETE")
print(f"{'='*80}")

mt5.shutdown()
