"""
live_bot.py — BOR Strategy live trading bot via MetaTrader 5 Python API.
Writes bor_state.json every poll cycle so the dashboard UI can read it.
"""

import sys, time, logging, json, os
import datetime
import pytz
from pathlib import Path
from logging.handlers import RotatingFileHandler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import MetaTrader5 as mt5
from bor_logic import BORStrategy, in_session, BORLevels, sort4
from trades_db import TradesDB
from performance_tracker import save_snapshot, get_stats
from python_mt5.alerts import (send_telegram, notify_trade, notify_close,
                               notify_error, notify_daily_pnl,
                               notify_risk_pause, notify_daily_reset)

ROOT          = Path(__file__).resolve().parent.parent
STATE_FILE    = ROOT / "bor_state.json"
SETTINGS_FILE = ROOT / "bor_settings.json"
LOG_FILE      = ROOT / "bor_live.log"
TRADES_DB_FILE = ROOT / "bor_trades.db.json"

handler = RotatingFileHandler(str(LOG_FILE), maxBytes=5*1024*1024, backupCount=3)
handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[handler, logging.StreamHandler()],
)
log = logging.getLogger("BOR-Live")
UTC = pytz.utc


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}

def _parse_time(t: str) -> tuple:
    h, m = t.split(":")
    return int(h), int(m)

def _broker_to_utc(t: tuple, offset_h: int) -> tuple:
    total = t[0] * 60 + t[1] - offset_h * 60
    total %= 1440
    return total // 60, total % 60


_cfg = _load_settings()

MT5_LOGIN    = int(_cfg.get("mt5_login", 0) or 0)
MT5_PASSWORD = str(_cfg.get("mt5_password", ""))
MT5_SERVER   = str(_cfg.get("mt5_server", ""))
MT5_PATH     = str(_cfg.get("mt5_path", ""))
INITIAL_BALANCE = float(_cfg.get("initial_balance", 10000))
RISK_PCT     = float(_cfg.get("risk_pct", 1.0))
MAX_TRADES_PER_SESSION = int(_cfg.get("max_trades_per_session", 2))
TP_MULTIPLIER = float(_cfg.get("tp_multiplier", 10))
POLL_INTERVAL = int(_cfg.get("poll_interval", 10))
TZ_OFFSET     = int(_cfg.get("timezone_offset", 0))

# Symbols — flat list of strings
_raw = _cfg.get("symbols", [])
SYMBOLS = [s if isinstance(s, str) else s["name"] for s in _raw]

# Sessions — convert broker time → UTC
_ses_cfg = _cfg.get("sessions", {})
_tky = _ses_cfg.get("tokyo",  {"enabled": True,  "start": "00:00", "end": "09:00"})
_ldn = _ses_cfg.get("london", {"enabled": True,  "start": "07:00", "end": "16:00"})

TOKYO_ENABLED  = _tky.get("enabled", True)
LONDON_ENABLED = _ldn.get("enabled", True)
TOKYO_START  = _broker_to_utc(_parse_time(_tky["start"]), TZ_OFFSET)
TOKYO_END    = _broker_to_utc(_parse_time(_tky["end"]),   TZ_OFFSET)
LONDON_START = _broker_to_utc(_parse_time(_ldn["start"]), TZ_OFFSET)
LONDON_END   = _broker_to_utc(_parse_time(_ldn["end"]),   TZ_OFFSET)


# ── state writer ──────────────────────────────────────────────────────────────

_state = {
    "connected":  False,
    "account":    0,
    "balance":    0.0,
    "equity":     0.0,
    "currency":   "USD",
    "server":     "",
    "symbols":    SYMBOLS,  # will be updated with resolved names after connect()
    "last_update": "",
    "sessions": {
        "tokyo":  {"active": False, "wins": 0, "losses": 0, "trades": 0},
        "london": {"active": False, "wins": 0, "losses": 0, "trades": 0},
    },
    "open_trades":  [],
    "trade_history": [],
    "logs": [],
}

_log_lines = []

class _UIHandler(logging.Handler):
    def emit(self, record):
        _log_lines.append(self.format(record))
        if len(_log_lines) > 100:
            _log_lines.pop(0)

_ui_handler = _UIHandler()
_ui_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s"))
logging.getLogger("BOR-Live").addHandler(_ui_handler)


def _save_state():
    _state["logs"] = list(_log_lines)
    _state["last_update"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    try:
        STATE_FILE.write_text(json.dumps(_state, indent=2))
    except Exception:
        pass


# ── Symbol name resolution ────────────────────────────────────────────────────

_RESOLVED_SYMBOLS = {}

def _resolve_symbol(symbol: str) -> str:
    """Resolve broker symbol name (e.g. 'EURUSD' -> 'EURUSDm' for Exness)."""
    if symbol in _RESOLVED_SYMBOLS:
        return _RESOLVED_SYMBOLS[symbol]
    info = mt5.symbol_info(symbol)
    if info is not None:
        _RESOLVED_SYMBOLS[symbol] = symbol
        return symbol
    for suffix in ('m', '.m', '-M', '.cash', '.spot', ''):
        candidate = symbol + suffix
        if candidate == symbol:
            continue
        info = mt5.symbol_info(candidate)
        if info is not None:
            _RESOLVED_SYMBOLS[symbol] = candidate
            log.info("Resolved symbol %s -> %s", symbol, candidate)
            return candidate
    log.warning("Could not resolve symbol %s, using as-is", symbol)
    _RESOLVED_SYMBOLS[symbol] = symbol
    return symbol

def _ensure_symbol(symbol: str) -> str:
    """Resolve and enable symbol in Market Watch."""
    sym = _resolve_symbol(symbol)
    mt5.symbol_select(sym, True)
    return sym


# ── Risk management state ──────────────────────────────────────────────────────

_risk = {
    "paused": False,
    "pause_until": None,
    "daily_start_balance": None,
    "daily_trades": {},       # per-symbol: {symbol: count}
    "consecutive_losses": 0,
    "last_notified_daily": None,
}


def _load_rm_config() -> dict:
    return _load_settings().get("risk_management", {})


def _check_risk_pause() -> bool:
    """Check if bot is in a risk pause. Returns True if trading should be blocked."""
    if _risk["pause_until"]:
        if datetime.datetime.now(datetime.timezone.utc) < _risk["pause_until"]:
            return True
        _risk["paused"] = False
        _risk["pause_until"] = None
        log.info("Risk pause ended — resuming trading")
    return False


def _check_risk_limits(symbol: str, session: str) -> tuple[bool, str]:
    """
    Check all risk limits.
    Returns (blocked: bool, reason: str).
    """
    rm = _load_rm_config()
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    # Daily reset
    if _risk["daily_start_balance"] is None:
        acct = mt5.account_info()
        if acct:
            _risk["daily_start_balance"] = acct.balance
            log.info("Daily risk tracking started — balance=%.2f", acct.balance)

    # Check max daily drawdown
    max_loss_pct = float(rm.get("max_daily_loss_pct", 5.0))
    if _risk["daily_start_balance"]:
        acct = mt5.account_info()
        if acct:
            loss_pct = (acct.balance - _risk["daily_start_balance"]) / _risk["daily_start_balance"] * 100
            if loss_pct <= -max_loss_pct:
                dur = 60
                _risk["pause_until"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=dur)
                _risk["paused"] = True
                msg = f"Max daily loss ({max_loss_pct}%) reached: {loss_pct:.1f}%. Pausing {dur}min"
                log.warning(msg)
                notify_risk_pause(msg)
                return True, msg

    # Check max daily trades (per-symbol, derived from max_trades_per_session × 2 sessions)
    sym_trades = _risk["daily_trades"].get(symbol, 0)
    cfg = _load_settings()
    max_per_session = int(cfg.get("max_trades_per_session", 2))
    max_daily = max_per_session * 2
    if sym_trades >= max_daily:
        msg = f"Max daily trades ({max_daily}) reached for {symbol}"
        log.warning(msg)
        return True, msg

    # Check consecutive loss limit
    max_cons = int(rm.get("consecutive_loss_limit", 3))
    if _risk["consecutive_losses"] >= max_cons:
        pause_min = int(rm.get("pause_after_loss_minutes", 15))
        _risk["pause_until"] = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=pause_min)
        _risk["paused"] = True
        msg = f"Consecutive loss limit ({max_cons}) hit — pausing {pause_min}min"
        log.warning(msg)
        notify_risk_pause(msg)
        return True, msg

    return False, ""


def _record_trade_result(outcome: str, symbol: str):
    """Update risk state after a trade closes."""
    if outcome == "sl":
        _risk["consecutive_losses"] += 1
    elif outcome == "tp":
        _risk["consecutive_losses"] = 0
    _risk["daily_trades"][symbol] = _risk["daily_trades"].get(symbol, 0) + 1


def _record_daily_notification(balance: float):
    """Send daily P&L notification at session transition."""
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    if _risk["last_notified_daily"] != today:
        _risk["last_notified_daily"] = today
        daily = _trades_db.get_daily_pnl(today)
        notify_daily_pnl(today, daily["pnl"], daily["trades"],
                         daily["wins"], daily["losses"], balance)
        # Reset daily tracking
        _risk["daily_start_balance"] = balance
        _risk["daily_trades"].clear()
        notify_daily_reset(daily["pnl"], balance)


# ── H1 Trend Filter ───────────────────────────────────────────────────────────

def _load_h1_config() -> dict:
    return _load_settings().get("h1_trend_filter", {})


def _get_h1_trend(symbol: str) -> str:
    """Check H1 trend using EMA. Returns 'bullish', 'bearish', or 'neutral'."""
    cfg = _load_h1_config()
    if not cfg.get("enabled", True):
        return "neutral"
    ema_period = int(cfg.get("ema_period", 20))
    lookback = int(cfg.get("lookback_candles", 24))
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, lookback + ema_period)
    if rates is None or len(rates) < ema_period + 2:
        return "neutral"
    closes = [r["close"] for r in rates]
    # Simple EMA
    k = 2 / (ema_period + 1)
    ema = closes[:ema_period]
    ema_val = sum(ema) / ema_period
    for price in closes[ema_period:]:
        ema_val = price * k + ema_val * (1 - k)
    # Compare last 2 closes to EMA
    last_close = closes[-1]
    prev_close = closes[-2]
    above_ema = last_close > ema_val and prev_close > ema_val
    below_ema = last_close < ema_val and prev_close < ema_val
    if above_ema:
        return "bullish"
    if below_ema:
        return "bearish"
    return "neutral"


# ── MT5 helpers ───────────────────────────────────────────────────────────────

def connect():
    kwargs = dict(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if MT5_PATH:
        kwargs["path"] = MT5_PATH
    if not mt5.initialize(**kwargs):
        log.error("MT5 init failed: %s", mt5.last_error())
        sys.exit(1)
    info = mt5.account_info()
    _state["connected"] = True
    _state["account"]   = info.login
    _state["balance"]   = info.balance
    _state["equity"]    = info.equity
    _state["currency"]  = info.currency
    _state["server"]    = MT5_SERVER
    # Resolve symbols to their broker names
    resolved = []
    for sym in SYMBOLS:
        resolved.append(_resolve_symbol(sym))
    _state["symbols"] = resolved
    global _RESOLVED_SYMBOLS
    _RESOLVED_SYMBOLS = dict(zip(SYMBOLS, resolved))
    log.info("Connected — account %d  balance %.2f %s  symbols: %s",
             info.login, info.balance, info.currency, resolved)


def get_balance() -> float:
    return mt5.account_info().balance


def get_15m_candles(symbol: str, count: int = 3):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 1, count)
    if rates is None or len(rates) == 0:
        return []
    bars = []
    for r in rates:
        bars.append({
            "time":  datetime.datetime.fromtimestamp(r["time"], tz=UTC),
            "open":  r["open"], "high": r["high"],
            "low":   r["low"],  "close": r["close"],
        })
    return bars


def calc_lot(symbol: str, entry: float, sl: float) -> float:
    """Calculate lot size to risk exactly RISK_PCT of INITIAL_BALANCE (from settings)."""
    risk_usd = INITIAL_BALANCE * RISK_PCT / 100.0
    sym_info = mt5.symbol_info(symbol)
    
    if sym_info is None:
        log.error("Symbol info not available for %s", symbol)
        return 0.01
    
    # SL distance in price units
    sl_distance = abs(entry - sl)
    if sl_distance == 0:
        log.warning("SL distance is zero for %s", symbol)
        return sym_info.volume_min
    
    # Get tick size and tick value
    tick_size = sym_info.trade_tick_size
    tick_value = sym_info.trade_tick_value
    
    # Calculate how many ticks in the SL distance
    ticks_in_sl = sl_distance / tick_size
    
    # Check if this is a forex pair (contract size = 100,000)
    # Exclude commodities like USOIL, UKOIL even if they have 100k contract size
    symbol_upper = symbol.upper()
    is_commodity = any(x in symbol_upper for x in ['OIL', 'XAU', 'GOLD', 'XAG', 'SILVER', 'US30', 'USTEC', 'NAS', 'DOW'])
    is_forex = sym_info.trade_contract_size == 100000.0 and not is_commodity
    
    if is_forex:
        # For forex, calculate pip value properly
        tick = mt5.symbol_info_tick(symbol)
        if tick:
            current_price = (tick.ask + tick.bid) / 2
        else:
            current_price = entry
        
        # Check if this is a JPY pair (2-3 decimal places)
        if sym_info.digits == 3 or sym_info.digits == 2:
            pip_size = 0.01
        else:
            pip_size = 0.0001
        
        symbol_upper = symbol.upper()
        if 'USD' in symbol_upper:
            if symbol_upper.startswith('USD'):
                # USDXXX pair (USD is base currency)
                pip_value_per_lot = (pip_size * sym_info.trade_contract_size) / current_price
            else:
                # XXXUSD pair (USD is quote currency)
                pip_value_per_lot = pip_size * sym_info.trade_contract_size
        else:
            # Cross pair (no USD) - use tick_value from MT5
            pip_value_per_lot = tick_value * (pip_size / tick_size)
        
        # Calculate lot size based on pips in SL
        pips_in_sl = sl_distance / pip_size
        lot = risk_usd / (pips_in_sl * pip_value_per_lot)
        
        log.info("%s lot calc: risk=$%.2f sl_dist=%.5f pips=%.2f pip_val=$%.2f → lot=%.2f",
                 symbol, risk_usd, sl_distance, pips_in_sl, pip_value_per_lot, lot)
    else:
        # For indices/commodities (XAUUSD, USTEC, US30, etc.)
        # Formula: lot = risk_usd / (sl_distance × tick_value / tick_size)
        
        # Get contract size
        contract_size = sym_info.trade_contract_size
        
        # CRITICAL: For gold with tick_size=0.001, we need to calculate correctly
        # XAUUSDm: tick_size=0.001, tick_value=0.1, contract_size=100
        # Standard XAUUSD: tick_size=0.01, tick_value=0.01, contract_size=100
        # 
        # The key insight: tick_value already accounts for contract_size
        # tick_value = value of 1 tick for 1 lot
        # 
        # For XAUUSDm: 1 tick (0.001) = $0.1 per lot
        # So 1.0 move = 1000 ticks = $100 per lot
        # 
        # Formula: value_per_unit = tick_value / tick_size
        # XAUUSDm: 0.1 / 0.001 = 100 (correct!)
        # US30m: 0.1 / 0.1 = 1 (correct!)
        
        if tick_size > 0:
            value_per_unit = tick_value / tick_size
        else:
            value_per_unit = tick_value
        
        # Calculate lot size
        # risk_usd = lot × sl_distance × value_per_unit
        # lot = risk_usd / (sl_distance × value_per_unit)
        lot = risk_usd / (sl_distance * value_per_unit)
        
        log.info("%s lot calc: risk=$%.2f sl_dist=%.2f tick_size=%.5f tick_val=%.5f value_per_unit=%.2f → lot=%.2f",
                 symbol, risk_usd, sl_distance, tick_size, tick_value, value_per_unit, lot)
    
    # Round to broker's volume step and clamp to min/max
    lot = round(lot / sym_info.volume_step) * sym_info.volume_step
    lot = max(sym_info.volume_min, min(sym_info.volume_max, lot))
    
    return lot


def place_order(symbol: str, direction: str, lot: float,
                entry: float, sl: float, tp: float, current_close: float) -> int:
    tick = mt5.symbol_info_tick(symbol)
    sym_info = mt5.symbol_info(symbol)
    
    # Get current spread
    spread = tick.ask - tick.bid
    
    # Check spread against max allowed
    rm = _load_rm_config()
    max_spread_pips = float(rm.get("max_spread_pips", 50))
    if sym_info:
        spread_pips = spread / (10 ** -(sym_info.digits - 1)) if sym_info.digits > 1 else spread * 10000
    else:
        spread_pips = spread * 10000
    if spread_pips > max_spread_pips:
        log.warning("%s spread too high (%.1f pips > %.0f limit) — skipping", symbol, spread_pips, max_spread_pips)
        return 0
    
    # Calculate ORIGINAL SL distance from entry (before any adjustments)
    original_sl_distance = abs(entry - sl)
    
    # Check if breakout candle has already covered > 15% of TP distance
    total_tp_distance = abs(tp - entry)
    if direction == "buy":
        distance_covered = current_close - entry
    else:
        distance_covered = entry - current_close
    
    tp_coverage_pct = (distance_covered / total_tp_distance * 100) if total_tp_distance > 0 else 0
    
    # Only apply spread buffer if SL is dangerously tight (< 2× spread)
    sl_adjusted = sl
    buffer_applied = False
    
    if original_sl_distance < (spread * 2):
        spread_buffer = spread * 1.5
        if direction == "buy":
            sl_adjusted = sl - spread_buffer
        else:
            sl_adjusted = sl + spread_buffer
        buffer_applied = True
        log.info("SL too tight (%.5f < 2×spread %.5f) - applying buffer: original_sl=%.5f adjusted_sl=%.5f",
                 original_sl_distance, spread * 2, sl, sl_adjusted)
    
    # If SL was adjusted, recalculate TP to maintain R:R and lot to keep dollar risk constant
    if sl_adjusted != sl:
        original_sl_dist = abs(entry - sl)
        new_sl_dist = abs(entry - sl_adjusted)
        if original_sl_dist > 0:
            rr = abs(tp - entry) / original_sl_dist
            new_tp_dist = new_sl_dist * rr
            if direction == "buy":
                tp = entry + new_tp_dist
            else:
                tp = entry - new_tp_dist
        lot = calc_lot(symbol, entry, sl_adjusted)
    
    # Decide: MARKET order or LIMIT order based on retracement config
    # (must match bor_logic.py logic: retrace_enabled AND coverage > threshold)
    retrace_cfg = _load_settings().get("retracement", {})
    retrace_enabled = bool(retrace_cfg.get("enabled", True))
    coverage_threshold = float(retrace_cfg.get("coverage_threshold", 0.0))

    if retrace_enabled and tp_coverage_pct > coverage_threshold:
        # Breakout candle covered > threshold of TP → place LIMIT order at breakout level
        order_type = mt5.ORDER_TYPE_BUY_LIMIT if direction == "buy" else mt5.ORDER_TYPE_SELL_LIMIT
        limit_price = entry
        
        request = {
            "action":       mt5.TRADE_ACTION_PENDING,
            "symbol":       symbol,
            "volume":       lot,
            "type":         order_type,
            "price":        limit_price,
            "sl":           sl_adjusted,
            "tp":           tp,
            "deviation":    20,
            "magic":        20240101,
            "comment":      "BOR_Bot_Limit",
            "type_time":    mt5.ORDER_TIME_GTC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error("Limit order failed %s %s: %s", symbol, direction, result.comment)
            return 0
        
        log.info("LIMIT order placed (retrace enabled, coverage %.1f%% > %.0f%%)  %s %s  lot=%.2f  limit=%.5f  SL=%.5f  TP=%.5f  ticket=%d",
                 tp_coverage_pct, coverage_threshold, symbol, direction.upper(), lot, limit_price, sl_adjusted, tp, result.order)
        return result.order
    
    else:
        # Retrace disabled or coverage below threshold → place MARKET order immediately
        order_type = mt5.ORDER_TYPE_BUY if direction == "buy" else mt5.ORDER_TYPE_SELL
        
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       lot,
            "type":         order_type,
            "price":        tick.ask if direction == "buy" else tick.bid,
            "sl":           sl_adjusted,
            "tp":           tp,
            "deviation":    20,
            "magic":        20240101,
            "comment":      "BOR_Bot",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            log.error("Market order failed %s %s: %s", symbol, direction, result.comment)
            return 0
        
        final_sl_dist = abs(entry - sl_adjusted)
        rr_ratio = (abs(tp - entry) / final_sl_dist) if final_sl_dist > 0 else 0
        sl_label = f"{sl_adjusted:.5f} (adjusted from {sl:.5f})" if sl_adjusted != sl else f"{sl:.5f}"
        log.info("MARKET order placed (coverage %.1f%%)  %s %s  lot=%.2f  entry=%.5f  SL=%s  TP=%.5f  R/R=1:%.1f  ticket=%d",
                 tp_coverage_pct, symbol, direction.upper(), lot, entry, sl_label, tp, rr_ratio, result.order)
        
        return result.order


def close_position(ticket: int, symbol: str, direction: str, lot: float):
    close_type = mt5.ORDER_TYPE_SELL if direction == "buy" else mt5.ORDER_TYPE_BUY
    tick  = mt5.symbol_info_tick(symbol)
    price = tick.bid if direction == "buy" else tick.ask
    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         close_type,
        "position":     ticket,
        "price":        price,
        "deviation":    20,
        "magic":        20240101,
        "comment":      "BOR_Bot_close",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        log.error("Close failed ticket %d: %s", ticket, result.comment)


# ── per-symbol bot ────────────────────────────────────────────────────────────

# Initialize trades database
_trades_db = TradesDB(TRADES_DB_FILE)

def _symbol_per_config(sym: str) -> dict:
    """Retrieve per-symbol config from symbols_config, falling back to globals."""
    base = sym.upper()
    for sfx in ('M', '.M', '-M'):
        if base.endswith(sfx):
            base = base[:-len(sfx)]
            break
    cfg = _load_settings()
    sc = cfg.get("symbols_config", {}).get(base, {})
    return {
        "tp_mult": float(sc.get("tp_multiplier", cfg.get("tp_multiplier", 10))),
        "min_range_points": float(sc.get("min_range_points", cfg.get("min_range_points", 0))),
        "min_stop_points": int(sc.get("min_stop_points", 0)),
        "retrace_enabled": sc.get("retrace_enabled") if "retrace_enabled" in sc else cfg.get("retracement", {}).get("enabled", True),
        "retrace_max_bars": int(sc.get("retrace_max_bars", cfg.get("retracement", {}).get("max_wait_bars", 50))),
        "retrace_coverage_threshold": float(sc.get("retrace_coverage_threshold", cfg.get("retracement", {}).get("coverage_threshold", 0.0))),
    }

class SymbolBot:
    def __init__(self, symbol: str):
        self.symbol   = _ensure_symbol(symbol)
        self.raw_symbol = symbol  # keep original name for settings/display
        pc = _symbol_per_config(symbol)
        min_stop_dist = 0.0
        if pc["min_stop_points"] > 0:
            info = mt5.symbol_info(self.symbol)
            if info:
                min_stop_dist = pc["min_stop_points"] * info.point
        self.strategy = BORStrategy(
            symbol=symbol, risk_pct=RISK_PCT,
            account_balance_fn=lambda: INITIAL_BALANCE,
            max_trades=MAX_TRADES_PER_SESSION, tp_mult=pc["tp_mult"],
            tokyo_start=TOKYO_START,   tokyo_end=TOKYO_END,
            london_start=LONDON_START, london_end=LONDON_END,
            min_range_points=pc["min_range_points"],
            min_stop_distance=min_stop_dist,
            retrace_enabled=pc["retrace_enabled"],
            retrace_max_bars=pc["retrace_max_bars"],
            retrace_coverage_threshold=pc["retrace_coverage_threshold"],
        )
        self.last_bar_time = None
        self.open_positions: dict = {}
        self.pending_orders: dict = {}  # Track pending limit orders with their TP levels
        self._tky_date = None  # Track last Tokyo session date
        self._ldn_date = None  # Track last London session date
        
        # Restore open positions from database on startup
        self._restore_from_db()

    def tick(self):
        # 15-min candles — used for BOTH BOR level snapshotting AND signal detection
        bars_15m = get_15m_candles(self.symbol, 3)
        if len(bars_15m) < 2:
            return

        latest_15m = bars_15m[-1]
        if latest_15m["time"] == self.last_bar_time:
            return

        prev_15m = bars_15m[-2]   # last closed 15-min candle (pre-session levels)
        cur_15m  = bars_15m[-1]   # current/opening 15-min candle (session open levels)
        utc_dt   = latest_15m["time"]

        # Check if we're entering a new session and need to reset trade_count
        tky_in = in_session(utc_dt, self.strategy.tokyo.start, self.strategy.tokyo.end)
        ldn_in = in_session(utc_dt, self.strategy.london.start, self.strategy.london.end)

        is_first_tick = self.last_bar_time is None

        # Per-day session init — uses (session_start, session_start+15min) pair
        # to compute levels, matching the backtest exactly
        tky_date = utc_dt.date()
        if tky_in and (self._tky_date is None or self._tky_date != tky_date):
            self._init_session_from_history("tokyo", utc_dt, _trades_db)
            self._tky_date = tky_date
            if not is_first_tick:
                log.info("%s: New Tokyo session — trade_count reset", self.symbol)

        ldn_date = utc_dt.date()
        if ldn_in and (self._ldn_date is None or self._ldn_date != ldn_date):
            self._init_session_from_history("london", utc_dt, _trades_db)
            self._ldn_date = ldn_date
            if not is_first_tick:
                log.info("%s: New London session — trade_count reset", self.symbol)

        self.last_bar_time = latest_15m["time"]

        # Sync with MT5: check if any positions for this symbol exist that we're not tracking
        mt5_positions = mt5.positions_get(symbol=self.symbol)
        if mt5_positions:
            for pos in mt5_positions:
                # Check if this is a BOR bot trade (magic number 20240101 or 99999999)
                if pos.magic in (20240101, 99999999) and pos.ticket not in self.open_positions:
                    # Determine which session this trade belongs to based on current active session
                    tky_in = in_session(utc_dt, self.strategy.tokyo.start, self.strategy.tokyo.end)
                    ldn_in = in_session(utc_dt, self.strategy.london.start, self.strategy.london.end)
                    
                    # Priority: London > Tokyo when both active
                    if ldn_in:
                        session = "london"
                    elif tky_in:
                        session = "tokyo"
                    else:
                        session = "manual"
                    
                    # Add to tracking
                    self.open_positions[pos.ticket] = {
                        "ticket":    pos.ticket,
                        "symbol":    self.symbol,
                        "direction": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
                        "session":   session,
                        "entry":     round(pos.price_open, 5),
                        "sl":        round(pos.sl, 5) if pos.sl else 0,
                        "tp":        round(pos.tp, 5) if pos.tp else 0,
                        "lot":       pos.volume,
                        "time":      datetime.datetime.fromtimestamp(pos.time, tz=UTC).strftime("%Y-%m-%d %H:%M"),
                        "pnl":       round(pos.profit, 2),
                    }
                    log.info("Synced existing position %d (%s %s) to %s session", 
                             pos.ticket, self.symbol, "BUY" if pos.type == mt5.ORDER_TYPE_BUY else "SELL", session.upper())

        # CRITICAL: Sync strategy trade_count with database BEFORE generating signals
        db_stats = _trades_db.get_session_stats(self.symbol)
        self.strategy.tokyo.trade_count = db_stats.get("tokyo", {}).get("trade_count", 0)
        self.strategy.london.trade_count = db_stats.get("london", {}).get("trade_count", 0)
        
        signals = self.strategy.on_candle(
            utc_dt=utc_dt,
            high=latest_15m["high"], low=latest_15m["low"],
            close=latest_15m["close"], prev_close=prev_15m["close"],
            pre_h=prev_15m["high"], pre_l=prev_15m["low"],
            open_h=cur_15m["high"], open_l=cur_15m["low"],
        )

        for sig in signals:
            session = sig["session"]
            current_trade_count = _trades_db.get_trade_count(self.symbol, session)
            
            # Double-check limit hasn't been exceeded (strategy already checked, but verify)
            if current_trade_count >= MAX_TRADES_PER_SESSION:
                log.warning("%s: Signal BLOCKED - %s session at limit %d/%d trades",
                           self.symbol, session.upper(), current_trade_count, MAX_TRADES_PER_SESSION)
                continue
            
            # H1 Trend Filter
            h1_cfg = _load_h1_config()
            if h1_cfg.get("enabled", True) and h1_cfg.get("only_trade_with_trend", True):
                trend = _get_h1_trend(self.symbol)
                dir = sig["direction"]
                if trend == "bearish" and dir == "buy":
                    log.info("%s: H1 trend BEARISH — blocking BUY signal", self.symbol)
                    continue
                if trend == "bullish" and dir == "sell":
                    log.info("%s: H1 trend BULLISH — blocking SELL signal", self.symbol)
                    continue
                log.info("%s: H1 trend %s — OK for %s", self.symbol, trend, dir.upper())
            
            # Risk management check
            blocked, reason = _check_risk_limits(self.symbol, session)
            if blocked:
                log.warning("%s: Risk limit BLOCKED %s - %s", self.symbol, session.upper(), reason)
                continue
            
            lot = calc_lot(self.symbol, sig["entry"], sig["sl"])
            ticket = place_order(self.symbol, sig["direction"],
                                 lot, sig["entry"], sig["sl"], sig["tp"], latest_15m["close"])
            if ticket:
                # Increment trade_count ONCE when order is placed
                _trades_db.increment_trade_count(self.symbol, session)
                new_count = _trades_db.get_trade_count(self.symbol, session)
                log.info("%s: Order placed - %s session count: %d/%d",
                        self.symbol, session.upper(), new_count, MAX_TRADES_PER_SESSION)
                
                # Check if this is a pending limit order
                mt5_pos = mt5.positions_get(ticket=ticket)
                if not mt5_pos:
                    # Pending limit order - track for monitoring
                    self.pending_orders[ticket] = {
                        "ticket": ticket,
                        "symbol": self.symbol,
                        "direction": sig["direction"],
                        "entry": sig["entry"],
                        "tp": sig["tp"],
                        "session": sig["session"],
                        "counted": True,  # Already counted when placed
                    }
                    log.info("Pending limit order %d - will cancel if TP reached", ticket)
                    notify_trade(self.symbol, sig["direction"], sig["session"],
                                 sig["entry"], sig["sl"], sig["tp"], lot,
                                 ticket, "LIMIT")
                else:
                    # Market order filled immediately
                    trade_data = {
                        "ticket":    ticket,
                        "symbol":    self.symbol,
                        "direction": sig["direction"],
                        "session":   sig["session"],
                        "entry":     round(sig["entry"], 5),
                        "sl":        round(sig["sl"],    5),
                        "tp":        round(sig["tp"],    5),
                        "lot":       lot,
                        "time":      utc_dt.strftime("%Y-%m-%d %H:%M"),
                        "pnl":       0.0,
                    }
                    self.open_positions[ticket] = trade_data
                    _trades_db.add_open_trade(ticket, trade_data)
                    log.info("Market order filled - %s %s in %s session",
                            self.symbol, sig["direction"].upper(), session.upper())
                    notify_trade(self.symbol, sig["direction"], sig["session"],
                                 sig["entry"], sig["sl"], sig["tp"], lot,
                                 ticket, "MARKET")
        
        # Monitor pending limit orders and cancel if price reaches TP
        self._monitor_pending_orders()

        # Check for session end and close trades if needed
        for ses in (self.strategy.tokyo, self.strategy.london):
            if not in_session(utc_dt, ses.start, ses.end):
                t = self.strategy.active_trade
                if t and not t.closed and t.session == ses.name:
                    if t.ticket and t.ticket in self.open_positions:
                        d, lv = self.open_positions[t.ticket]["direction"], self.open_positions[t.ticket]["lot"]
                        close_position(t.ticket, self.symbol, d, lv)
                        closed = self.open_positions.pop(t.ticket)
                        _add_history(closed, "session_end")

    def _monitor_pending_orders(self):
        """Monitor pending limit orders and cancel if price reaches TP without retracing to entry."""
        if not self.pending_orders:
            return
        
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            return
        
        current_price = tick.last
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        
        # Check if sessions are active
        tky_active = in_session(utc_now, self.strategy.tokyo.start, self.strategy.tokyo.end)
        ldn_active = in_session(utc_now, self.strategy.london.start, self.strategy.london.end)
        
        for ticket in list(self.pending_orders.keys()):
            order_info = self.pending_orders[ticket]
            direction = order_info["direction"]
            entry = order_info["entry"]
            tp = order_info["tp"]
            order_session = order_info["session"]
            
            # Check if order still exists in MT5
            mt5_order = mt5.orders_get(ticket=ticket)
            if not mt5_order:
                # Order no longer exists (filled or cancelled)
                mt5_pos = mt5.positions_get(ticket=ticket)
                if mt5_pos:
                    # Limit order filled - move to open positions (already counted when placed)
                    pos = mt5_pos[0]
                    trade_data = {
                        "ticket":    ticket,
                        "symbol":    self.symbol,
                        "direction": direction,
                        "session":   order_info["session"],
                        "entry":     round(pos.price_open, 5),
                        "sl":        round(pos.sl, 5) if pos.sl else 0,
                        "tp":        round(pos.tp, 5) if pos.tp else 0,
                        "lot":       pos.volume,
                        "time":      datetime.datetime.fromtimestamp(pos.time, tz=UTC).strftime("%Y-%m-%d %H:%M"),
                        "pnl":       0.0,
                    }
                    self.open_positions[ticket] = trade_data
                    _trades_db.add_open_trade(ticket, trade_data)
                    log.info("Limit order %d filled at %.5f (already counted)", ticket, pos.price_open)
                else:
                    # Order cancelled/expired - decrement count since it never filled
                    order_session = order_info["session"]
                    _trades_db.decrement_trade_count(self.symbol, order_session)
                    new_count = _trades_db.get_trade_count(self.symbol, order_session)
                    log.info("Limit order %d cancelled - %s session count: %d/%d",
                            ticket, order_session.upper(), new_count, MAX_TRADES_PER_SESSION)
                
                del self.pending_orders[ticket]
                continue
            
            # Check if order should be cancelled due to session end
            should_cancel = False
            cancel_reason = ""
            
            if order_session == "tokyo":
                # Tokyo orders: cancel if London starts OR Tokyo ends
                if ldn_active:
                    should_cancel = True
                    cancel_reason = "London session started (Tokyo levels invalid)"
                elif not tky_active:
                    should_cancel = True
                    cancel_reason = "Tokyo session ended"
            
            elif order_session == "london":
                # London orders: cancel if London ends
                if not ldn_active:
                    should_cancel = True
                    cancel_reason = "London session ended"
            
            # Check if price has reached TP without retracing to entry
            if not should_cancel:
                if direction == "buy":
                    # For BUY: cancel if price reached TP (above) without retracing to entry (below)
                    if current_price >= tp:
                        should_cancel = True
                        cancel_reason = f"price {current_price:.5f} reached TP {tp:.5f} without retracing to entry {entry:.5f}"
                else:
                    # For SELL: cancel if price reached TP (below) without retracing to entry (above)
                    if current_price <= tp:
                        should_cancel = True
                        cancel_reason = f"price {current_price:.5f} reached TP {tp:.5f} without retracing to entry {entry:.5f}"
            
            if should_cancel:
                # Cancel the pending order
                request = {
                    "action": mt5.TRADE_ACTION_REMOVE,
                    "order": ticket,
                }
                result = mt5.order_send(request)
                if result.retcode == mt5.TRADE_RETCODE_DONE:
                    # Decrement count since order was counted when placed but never filled
                    order_session = order_info["session"]
                    _trades_db.decrement_trade_count(self.symbol, order_session)
                    new_count = _trades_db.get_trade_count(self.symbol, order_session)
                    log.info("%s limit order %d CANCELLED: %s - %s session count: %d/%d",
                            direction.upper(), ticket, cancel_reason, order_session.upper(), 
                            new_count, MAX_TRADES_PER_SESSION)
                else:
                    log.error("Failed to cancel limit order %d: %s", ticket, result.comment)
                
                del self.pending_orders[ticket]
    
    def get_open(self):
        return list(self.open_positions.values())
    
    def _restore_from_db(self):
        """Restore open positions from database on bot startup"""
        all_open = _trades_db.get_all_open_trades()
        for ticket, trade_data in all_open.items():
            if trade_data.get("symbol") == self.symbol:
                self.open_positions[ticket] = trade_data
                log.info("Restored position %d from database: %s %s in %s session", 
                         ticket, self.symbol, trade_data["direction"].upper(), trade_data["session"].upper())

    def _init_session_from_history(self, session_name: str, current_dt: datetime.datetime, trades_db):
        """Initialize session levels from historical M15 data when bot starts mid-session."""
        session = getattr(self.strategy, session_name)
        start_h, start_m = session.start

        session_start = current_dt.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        pre_bar_dt = session_start
        session_bar_dt = session_start + datetime.timedelta(minutes=15)
        fetch_to = current_dt + datetime.timedelta(minutes=30)

        # Always reset counts at session boundary (before early return)
        trades_db.reset_session_counts(self.symbol, session_name)
        session.trade_count = 0

        rates = mt5.copy_rates_range(self.symbol, mt5.TIMEFRAME_M15, pre_bar_dt, fetch_to)
        if rates is None or len(rates) < 2:
            log.warning("%s: No history for %s init — levels deferred to on_candle", self.symbol, session_name)
            return

        bars = []
        for r in rates:
            bars.append({
                "time": datetime.datetime.fromtimestamp(r["time"], tz=pytz.UTC),
                "high": float(r["high"]),
                "low":  float(r["low"]),
            })

        session_bar = None
        pre_bar = None
        for i, b in enumerate(bars):
            if b["time"] == session_bar_dt and i > 0:
                session_bar = b
                pre_bar = bars[i - 1]
                break

        if session_bar is None or pre_bar is None:
            log.warning("%s: Session-open+15m candle not found for %s — levels deferred to on_candle", self.symbol, session_name)
            return

        s1, s2, s3, s4 = sort4(pre_bar["high"], pre_bar["low"], session_bar["high"], session_bar["low"])
        session.levels = BORLevels(s1, s2, s3, s4)
        session.initialized = True

        # Re-sync DB to match open MT5 positions
        open_pos_count = 0
        try:
            positions = mt5.positions_get(symbol=self.symbol)
            if positions:
                for pos in positions:
                    if pos.magic in (20240101, 99999999):
                        open_pos_count += 1
        except Exception:
            pass
        for _ in range(open_pos_count):
            trades_db.increment_trade_count(self.symbol, session_name)
        session.trade_count = trades_db.get_trade_count(self.symbol, session_name)

        log.info("%s: %s initialized from history @ %s (levels: %.5f / %.5f / %.5f / %.5f, mt5_positions: %d)",
                 self.symbol, session_name.upper(), session_start.strftime("%H:%M"),
                 s1, s2, s3, s4, session.trade_count)

    def session_stats(self):
        # Re-read session times from settings each call so the dashboard
        # always reflects the current config even without a bot restart.
        now = datetime.datetime.now(datetime.timezone.utc)
        cfg      = _load_settings()
        tz       = int(cfg.get("timezone_offset", 0))
        ses_cfg  = cfg.get("sessions", {})
        tky_cfg  = ses_cfg.get("tokyo",  {"enabled": True,  "start": "00:00", "end": "09:00"})
        ldn_cfg  = ses_cfg.get("london", {"enabled": True,  "start": "07:00", "end": "16:00"})
        tky_s = _broker_to_utc(_parse_time(tky_cfg["start"]), tz)
        tky_e = _broker_to_utc(_parse_time(tky_cfg["end"]),   tz)
        ldn_s = _broker_to_utc(_parse_time(ldn_cfg["start"]), tz)
        ldn_e = _broker_to_utc(_parse_time(ldn_cfg["end"]),   tz)
        
        # Check if both sessions are active (London takes priority)
        tky_active = tky_cfg.get("enabled", True) and in_session(now, tky_s, tky_e)
        ldn_active = ldn_cfg.get("enabled", True) and in_session(now, ldn_s, ldn_e)
        
        # If both active, London takes priority and Tokyo levels are invalid
        if tky_active and ldn_active:
            tky_active = False
        
        # Format levels for display
        def format_levels(ses):
            if ses.initialized and ses.levels.valid:
                return f"S1:{ses.levels.s1:.5f} S2:{ses.levels.s2:.5f} S3:{ses.levels.s3:.5f} S4:{ses.levels.s4:.5f}"
            return "—"
        
        # Return stats based on where trades were OPENED, not current session
        return {
            "tokyo":  {
                "active":  tky_active,
                "wins":    self.strategy.tokyo_wins,
                "trades":  self.strategy.tokyo.trade_count,
                "losses":  self.strategy.tokyo_losses,
                "levels":  format_levels(self.strategy.tokyo),
            },
            "london": {
                "active":  ldn_active,
                "wins":    self.strategy.london_wins,
                "trades":  self.strategy.london.trade_count,
                "losses":  self.strategy.london_losses,
                "levels":  format_levels(self.strategy.london),
            },
        }


_trade_history = []

def _add_history(trade: dict, reason: str):
    trade = dict(trade)
    trade["close_reason"] = reason
    _trade_history.append(trade)
    if len(_trade_history) > 50:
        _trade_history.pop(0)


# ── main loop ─────────────────────────────────────────────────────────────────

def main():
    connect()
    bots = [SymbolBot(sym) for sym in SYMBOLS]
    log.info("BOR Bot started — symbols: %s", SYMBOLS)
    
    # Load closed trades from database into trade history
    global _trade_history
    closed_trades = _trades_db.get_closed_trades(limit=50)
    for trade in closed_trades:
        _trade_history.append(trade)
    log.info("Loaded %d closed trades from database", len(_trade_history))
    
    # Load per-symbol session stats from database and restore to each bot's strategy
    for bot in bots:
        symbol_stats = _trades_db.get_session_stats(bot.symbol)
        bot.strategy.tokyo_wins = symbol_stats.get("tokyo", {}).get("wins", 0)
        bot.strategy.tokyo_losses = symbol_stats.get("tokyo", {}).get("losses", 0)
        bot.strategy.tokyo.trade_count = symbol_stats.get("tokyo", {}).get("trade_count", 0)
        bot.strategy.london_wins = symbol_stats.get("london", {}).get("wins", 0)
        bot.strategy.london_losses = symbol_stats.get("london", {}).get("losses", 0)
        bot.strategy.london.trade_count = symbol_stats.get("london", {}).get("trade_count", 0)
        log.info("%s session stats loaded: Tokyo W/L/T=%d/%d/%d, London W/L/T=%d/%d/%d",
                 bot.symbol,
                 bot.strategy.tokyo_wins, bot.strategy.tokyo_losses, bot.strategy.tokyo.trade_count,
                 bot.strategy.london_wins, bot.strategy.london_losses, bot.strategy.london.trade_count)

    try:
        while True:
            for bot in bots:
                try:
                    bot.tick()
                except Exception as exc:
                    log.exception("Error on %s: %s", bot.symbol, exc)
                    notify_error(f"{bot.symbol}: {exc}")

            info = mt5.account_info()
            if info:
                _state["balance"] = round(info.balance, 2)
                _state["equity"]  = round(info.equity,  2)
                
                # Track performance history
                save_snapshot(info.balance, info.equity)

            # Get ALL open positions from MT5 in real-time
            all_positions = mt5.positions_get()
            open_trades_list = []
            
            if all_positions:
                for pos in all_positions:
                    # Get current price for this position
                    tick = mt5.symbol_info_tick(pos.symbol)
                    if tick:
                        if pos.type == mt5.ORDER_TYPE_BUY:
                            current_price = round(tick.bid, 5)
                        else:
                            current_price = round(tick.ask, 5)
                    else:
                        current_price = round(pos.price_open, 5)
                    
                    # Determine session (check if tracked by bot)
                    session = "manual"
                    for bot in bots:
                        if pos.ticket in bot.open_positions:
                            session = bot.open_positions[pos.ticket]["session"]
                            break
                    
                    # Log exact MT5 data for debugging
                    log.debug("MT5 Position #%d: symbol='%s' lot=%.2f entry=%.5f sl=%.5f tp=%.5f",
                             pos.ticket, pos.symbol, pos.volume, pos.price_open, 
                             pos.sl if pos.sl else 0, pos.tp if pos.tp else 0)
                    
                    open_trades_list.append({
                        "ticket": pos.ticket,
                        "symbol": pos.symbol,  # EXACT symbol name from MT5
                        "direction": "buy" if pos.type == mt5.ORDER_TYPE_BUY else "sell",
                        "session": session,
                        "entry": round(pos.price_open, 5),
                        "sl": round(pos.sl, 5) if pos.sl else 0,
                        "tp": round(pos.tp, 5) if pos.tp else 0,
                        "lot": pos.volume,  # EXACT lot size from MT5
                        "time": datetime.datetime.fromtimestamp(pos.time, tz=UTC).strftime("%Y-%m-%d %H:%M"),
                        "pnl": round(pos.profit, 2),
                        "current_price": current_price,
                    })
            
            # Update bot's internal tracking to match MT5 reality
            for bot in bots:
                mt5_tickets = {p.ticket for p in all_positions} if all_positions else set()
                # Remove closed positions from bot tracking
                for ticket in list(bot.open_positions.keys()):
                    if ticket not in mt5_tickets:
                        closed = bot.open_positions.pop(ticket)
                        
                        # Get actual close price from MT5 deal history
                        deals = mt5.history_deals_get(position=ticket)
                        close_price = None
                        
                        if deals and len(deals) >= 2:
                            # Find the OUT deal (exit)
                            for deal in reversed(deals):
                                if deal.entry == mt5.DEAL_ENTRY_OUT:
                                    close_price = deal.price
                                    log.info("Position %d: Found OUT deal with close price %.5f", ticket, close_price)
                                    break
                        
                        # Fallback to current price if no deal found
                        if close_price is None:
                            close_price = closed.get("current_price", closed.get("entry"))
                            log.warning("Position %d: No OUT deal found, using fallback price %.5f", ticket, close_price)
                        
                        entry = closed.get("entry")
                        tp = closed.get("tp")
                        sl = closed.get("sl")
                        direction = closed.get("direction")
                        
                        # Determine close reason by comparing actual close price to TP/SL
                        # Use larger tolerance for indices (10 points) vs forex (10 pips)
                        symbol = closed.get("symbol", "")
                        if any(x in symbol.upper() for x in ['US30', 'USTEC', 'NAS', 'DOW']):
                            tolerance = 10.0  # 10 points for indices
                        elif 'XAU' in symbol.upper() or 'GOLD' in symbol.upper():
                            tolerance = 1.0   # $1 for gold
                        else:
                            tolerance = 0.001  # 10 pips for forex
                        
                        close_reason = "closed"
                        
                        if tp and sl:
                            tp_diff = abs(close_price - tp)
                            sl_diff = abs(close_price - sl)
                            
                            log.info("Position %d: close=%.5f tp=%.5f (diff=%.5f) sl=%.5f (diff=%.5f) tolerance=%.5f",
                                   ticket, close_price, tp, tp_diff, sl, sl_diff, tolerance)
                            
                            # Check which is closer and within tolerance
                            if tp_diff <= tolerance and tp_diff < sl_diff:
                                close_reason = "tp"
                            elif sl_diff <= tolerance and sl_diff < tp_diff:
                                close_reason = "sl"
                        
                        # Get ACTUAL P&L from MT5 deal history
                        actual_pnl = None
                        if deals and len(deals) >= 2:
                            # Calculate total P&L from all deals for this position
                            actual_pnl = sum(deal.profit for deal in deals)
                            log.info("Position %d: Actual P&L from MT5 deals = $%.2f", ticket, actual_pnl)
                        
                        log.info("Position %d closed at %.5f by %s - %s", ticket, close_price, close_reason.upper(), bot.symbol)
                        
                        # Send close alert
                        notify_close(
                            closed.get("symbol", ""), closed.get("direction", ""),
                            closed.get("session", ""), closed.get("entry", 0),
                            close_price, actual_pnl or 0, close_reason, ticket
                        )
                        
                        # Update risk management state
                        _record_trade_result(close_reason, bot.symbol)
                        
                        # Save to database as closed WITH actual P&L
                        _trades_db.close_trade(ticket, {
                            "close_reason": close_reason,
                            "close_price": close_price,
                            "actual_pnl": actual_pnl if actual_pnl is not None else 0.0,
                        })
                        _add_history(closed, close_reason)
            
            # Sync database with MT5 (remove trades that no longer exist)
            _trades_db.sync_with_mt5(mt5_tickets if all_positions else set())
            
            _state["open_trades"] = open_trades_list
            _state["trade_history"] = list(_trade_history)

            # Aggregate session stats across all symbols
            # Each bot tracks trades by the session where they were OPENED
            for ses_name in ("tokyo", "london"):
                total_trades = 0
                total_wins = 0
                total_losses = 0
                is_active = False
                levels_list = []
                
                for bot in bots:
                    s = bot.session_stats()[ses_name]
                    is_active = is_active or s["active"]
                    total_trades += s["trades"]
                    total_wins += s["wins"]
                    total_losses += s["losses"]
                    if s.get("levels") and s["levels"] != "—":
                        levels_list.append(f"{bot.symbol}: {s['levels']}")
                
                # Format levels for display
                levels_display = "\n".join(levels_list) if levels_list else "—"
                
                _state["sessions"][ses_name] = {
                    "active": is_active,
                    "wins": total_wins,
                    "losses": total_losses,
                    "trades": total_trades,
                    "levels": levels_display,
                }

            _save_state()
            
            # Daily P&L notification (once per day)
            try:
                info = mt5.account_info()
                if info:
                    _record_daily_notification(info.balance)
            except Exception:
                pass
            
            time.sleep(POLL_INTERVAL)

    except KeyboardInterrupt:
        log.info("Shutting down...")
        _state["connected"] = False
        _save_state()
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
