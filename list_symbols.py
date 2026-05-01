"""
List all available symbols in MT5 to find correct names for XAUUSD and US30
"""

import MetaTrader5 as mt5
import json
from pathlib import Path

# Load settings
SETTINGS_FILE = Path(__file__).parent / "bor_settings.json"
cfg = json.loads(SETTINGS_FILE.read_text())

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
print("=" * 80)

# Get all symbols
symbols = mt5.symbols_get()
print(f"\nTotal symbols available: {len(symbols)}")

# Filter for gold and US30
print("\n" + "=" * 80)
print("GOLD SYMBOLS (containing XAU, GOLD):")
print("=" * 80)
gold_symbols = [s for s in symbols if 'XAU' in s.name.upper() or 'GOLD' in s.name.upper()]
for sym in gold_symbols:
    info = mt5.symbol_info(sym.name)
    print(f"  {sym.name:<20} | Contract: {info.trade_contract_size:>10,.0f} | Tick: {info.trade_tick_size:>8} | Tick Val: ${info.trade_tick_value:>8}")

print("\n" + "=" * 80)
print("DOW JONES SYMBOLS (containing US30, DOW, DJ):")
print("=" * 80)
dow_symbols = [s for s in symbols if any(x in s.name.upper() for x in ['US30', 'DOW', 'DJ30', 'US 30'])]
for sym in dow_symbols:
    info = mt5.symbol_info(sym.name)
    print(f"  {sym.name:<20} | Contract: {info.trade_contract_size:>10,.0f} | Tick: {info.trade_tick_size:>8} | Tick Val: ${info.trade_tick_value:>8}")

print("\n" + "=" * 80)
print("CURRENT CONFIGURED SYMBOLS:")
print("=" * 80)
configured = cfg.get("symbols", [])
for sym_name in configured:
    if isinstance(sym_name, dict):
        sym_name = sym_name.get("name", "")
    info = mt5.symbol_info(sym_name)
    if info:
        print(f"  {sym_name:<20} | Contract: {info.trade_contract_size:>10,.0f} | Tick: {info.trade_tick_size:>8} | Tick Val: ${info.trade_tick_value:>8}")
    else:
        print(f"  {sym_name:<20} | NOT FOUND IN MT5")

mt5.shutdown()
