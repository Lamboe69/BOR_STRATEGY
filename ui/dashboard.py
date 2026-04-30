"""
dashboard.py — BOR Strategy web dashboard (Flask).
Serves the live dashboard + settings page.
Manages the live bot as a subprocess.

Run:
    python ui/dashboard.py
"""

import json, sys, subprocess, signal, webbrowser, threading, os, hashlib, secrets, datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from functools import wraps

ROOT          = Path(__file__).resolve().parent.parent
STATE_FILE    = ROOT / "bor_state.json"
SETTINGS_FILE = ROOT / "bor_settings.json"
BOT_SCRIPT    = ROOT / "python_mt5" / "live_bot.py"
BACKTEST_FILE = ROOT / "bor_backtest.json"
USERS_FILE    = ROOT / "users.json"

sys.path.insert(0, str(ROOT))

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

_bot_process: subprocess.Popen | None = None


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}

def _save_settings(data: dict):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2))

def _bot_running() -> bool:
    return _bot_process is not None and _bot_process.poll() is None

def _load_users() -> dict:
    try:
        return json.loads(USERS_FILE.read_text())
    except Exception:
        return {"users": []}

def _save_users(data: dict):
    USERS_FILE.write_text(json.dumps(data, indent=2))

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login_page"))
        if session.get("role") != "admin":
            return jsonify({"ok": False, "msg": "Admin access required"}), 403
        return f(*args, **kwargs)
    return decorated


# ── routes ────────────────────────────────────────────────────────────────────

@app.route("/login")
def login_page():
    if session.get("logged_in"):
        return redirect(url_for("index"))
    return render_template("login.html")

@app.route("/auth/register", methods=["POST"])
def auth_register():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"ok": False, "msg": "Username and password required"}), 400
    
    if len(password) < 6:
        return jsonify({"ok": False, "msg": "Password must be at least 6 characters"}), 400
    
    users_data = _load_users()
    
    # SECURITY: Only allow registration if NO users exist (first-time setup)
    if len(users_data["users"]) > 0:
        return jsonify({"ok": False, "msg": "Registration is disabled. Contact the administrator."}), 403
    
    if any(u["username"] == username for u in users_data["users"]):
        return jsonify({"ok": False, "msg": "Username already exists"}), 400
    
    # First user is automatically admin with full access
    users_data["users"].append({
        "username": username,
        "password": _hash_password(password),
        "role": "admin",
        "created_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    })
    _save_users(users_data)
    
    return jsonify({"ok": True, "msg": "Admin account created successfully"})

@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True)
    username = data.get("username", "").strip()
    password = data.get("password", "")
    
    users_data = _load_users()
    user = next((u for u in users_data["users"] if u["username"] == username), None)
    
    if user and user["password"] == _hash_password(password):
        session["logged_in"] = True
        session["username"] = username
        session["role"] = user.get("role", "viewer")  # admin or viewer
        return jsonify({"ok": True})
    
    return jsonify({"ok": False, "msg": "Invalid username or password"}), 401

@app.route("/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"ok": True})

@app.route("/")
@login_required
def index():
    return render_template("index.html", active_page="dashboard")


@app.route("/performance_page")
@login_required
def performance_page():
    return render_template("performance.html", active_page="performance")


@app.route("/settings", methods=["GET"])
@login_required
def settings_page():
    return render_template("settings.html", settings=_load_settings(), active_page="settings")


@app.route("/settings", methods=["POST"])
@admin_required
def settings_save():
    data = request.get_json(force=True)
    
    # Check if bot is running
    bot_was_running = _bot_running()
    
    # Save settings
    _save_settings(data)
    
    # If bot was running, restart it to apply new settings
    if bot_was_running:
        global _bot_process
        try:
            # Stop the bot
            _bot_process.terminate()
            _bot_process.wait(timeout=5)
        except Exception:
            try:
                _bot_process.kill()
            except Exception:
                pass
        _bot_process = None
        
        # Wait a moment for cleanup
        import time
        time.sleep(1)
        
        # Start the bot with new settings
        try:
            _bot_process = subprocess.Popen(
                [sys.executable, str(BOT_SCRIPT)],
                cwd=str(ROOT)
            )
            return jsonify({"ok": True, "restarted": True, "msg": "Settings saved and bot restarted"})
        except Exception as e:
            return jsonify({"ok": False, "msg": f"Settings saved but failed to restart bot: {str(e)}"}), 500
    
    return jsonify({"ok": True, "restarted": False})


def _parse_time(t: str) -> tuple:
    h, m = t.split(":")
    return int(h), int(m)

def _broker_to_utc(t: tuple, offset_h: int) -> tuple:
    total = t[0] * 60 + t[1] - offset_h * 60
    total %= 1440
    return total // 60, total % 60

def _in_session(now_minutes: int, start: tuple, end: tuple) -> bool:
    s = start[0] * 60 + start[1]
    e = end[0]   * 60 + end[1]
    if s < e:
        return s <= now_minutes < e
    return now_minutes >= s or now_minutes < e

def _compute_active_sessions() -> dict:
    """Compute session active flags from current settings + current UTC time."""
    import datetime
    cfg     = _load_settings()
    tz      = int(cfg.get("timezone_offset", 0))
    ses_cfg = cfg.get("sessions", {})
    tky_cfg = ses_cfg.get("tokyo",  {"enabled": True, "start": "00:00", "end": "09:00"})
    ldn_cfg = ses_cfg.get("london", {"enabled": True, "start": "07:00", "end": "16:00"})

    now = datetime.datetime.now(datetime.timezone.utc)
    now_min = now.hour * 60 + now.minute

    tky_s = _broker_to_utc(_parse_time(tky_cfg.get("start", "00:00")), tz)
    tky_e = _broker_to_utc(_parse_time(tky_cfg.get("end",   "09:00")), tz)
    ldn_s = _broker_to_utc(_parse_time(ldn_cfg.get("start", "07:00")), tz)
    ldn_e = _broker_to_utc(_parse_time(ldn_cfg.get("end",   "16:00")), tz)

    return {
        "tokyo":  tky_cfg.get("enabled", True) and _in_session(now_min, tky_s, tky_e),
        "london": ldn_cfg.get("enabled", True) and _in_session(now_min, ldn_s, ldn_e),
    }


@app.route("/state")
@login_required
def state():
    running = _bot_running()
    try:
        s = json.loads(STATE_FILE.read_text())
    except Exception:
        s = {}
    s["bot_running"] = running

    # Always override active flags with fresh calculation from current settings
    active = _compute_active_sessions()
    for name in ("tokyo", "london"):
        if name not in s.get("sessions", {}):
            s.setdefault("sessions", {})[name] = {}
        s["sessions"][name]["active"] = active[name]

    # Inject UTC session start times so the JS countdown is always correct
    import datetime
    cfg     = _load_settings()
    tz      = int(cfg.get("timezone_offset", 0))
    ses_cfg = cfg.get("sessions", {})
    tky_cfg = ses_cfg.get("tokyo",  {"start": "00:00", "end": "09:00"})
    ldn_cfg = ses_cfg.get("london", {"start": "07:00", "end": "16:00"})
    tky_s_utc = _broker_to_utc(_parse_time(tky_cfg.get("start", "00:00")), tz)
    ldn_s_utc = _broker_to_utc(_parse_time(ldn_cfg.get("start", "07:00")), tz)
    s["session_starts_utc"] = {
        "tokyo":  {"h": tky_s_utc[0], "m": tky_s_utc[1]},
        "london": {"h": ldn_s_utc[0], "m": ldn_s_utc[1]},
    }

    # Inject server name from settings if bot hasn't populated it
    if not s.get("server"):
        s["server"] = _load_settings().get("mt5_server", "")

    return jsonify(s)


@app.route("/performance")
@login_required
def performance():
    """Return performance statistics and history for graphing"""
    try:
        sys.path.insert(0, str(ROOT))
        from performance_tracker import get_stats
        return jsonify(get_stats())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/performance/symbol/<symbol>")
@login_required
def performance_symbol(symbol):
    """Return performance data for a specific symbol based on ACTUAL closed trade P&L from MT5"""
    try:
        sys.path.insert(0, str(ROOT))
        from trades_db import TradesDB
        
        trades_db = TradesDB(ROOT / "bor_trades.db.json")
        all_closed = trades_db.get_closed_trades(limit=1000)
        
        # Filter trades for this symbol
        symbol_trades = [t for t in all_closed if t.get("symbol") == symbol]
        
        if not symbol_trades:
            return jsonify({
                "symbol": symbol,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "history": []
            })
        
        # Calculate cumulative P&L using ACTUAL trade results from MT5
        history = []
        cumulative_pnl = 0
        wins = 0
        losses = 0
        
        # Get settings for fallback calculation
        cfg = _load_settings()
        initial_balance = float(cfg.get("initial_balance", 10000))
        risk_pct = float(cfg.get("risk_pct", 1.0))
        tp_mult = float(cfg.get("tp_multiplier", 10))
        risk_per_trade = initial_balance * risk_pct / 100.0
        
        for trade in symbol_trades:
            close_reason = trade.get("close_reason", "closed")
            
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
            
            # Count wins/losses based on P&L
            if pnl > 0:
                wins += 1
            elif pnl < 0:
                losses += 1
            
            cumulative_pnl += pnl
            
            history.append({
                "time": trade.get("closed_at", trade.get("time", "")),
                "pnl": round(pnl, 2),
                "cumulative_pnl": round(cumulative_pnl, 2),
                "close_reason": close_reason,
                "direction": trade.get("direction", ""),
                "session": trade.get("session", "")
            })
        
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        return jsonify({
            "symbol": symbol,
            "total_trades": total_trades,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(cumulative_pnl, 2),
            "history": history
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/bot/start", methods=["POST"])
@admin_required
def bot_start():
    global _bot_process
    if _bot_running():
        return jsonify({"ok": True, "msg": "already running"})
    try:
        _bot_process = subprocess.Popen(
            [sys.executable, str(BOT_SCRIPT)],
            cwd=str(ROOT)
        )
        return jsonify({"ok": True, "pid": _bot_process.pid})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/bot/stop", methods=["POST"])
@admin_required
def bot_stop():
    global _bot_process
    if not _bot_running():
        return jsonify({"ok": True, "msg": "not running"})
    try:
        _bot_process.terminate()
        _bot_process.wait(timeout=5)
    except Exception:
        try:
            _bot_process.kill()
        except Exception:
            pass
    _bot_process = None
    # mark state as disconnected
    try:
        s = json.loads(STATE_FILE.read_text())
        s["connected"] = False
        s["bot_running"] = False
        STATE_FILE.write_text(json.dumps(s, indent=2))
    except Exception:
        pass
    return jsonify({"ok": True})


@app.route("/backtest")
@login_required
def backtest_page():
    return render_template("backtest.html", active_page="backtest")


@app.route("/backtest/symbols")
@login_required
def backtest_symbols():
    """Return available symbols from MT5 if reachable, else fall back to settings."""
    cfg = _load_settings()
    fallback = cfg.get("symbols", ["EURUSD", "XAUUSD", "US30", "USTEC"])
    try:
        import MetaTrader5 as mt5
        login    = int(cfg.get("mt5_login", 0))
        password = cfg.get("mt5_password", "")
        server   = cfg.get("mt5_server", "")
        path     = cfg.get("mt5_path", "") or None
        kwargs   = {"login": login, "password": password, "server": server}
        if path:
            kwargs["path"] = path
        if not mt5.initialize(**kwargs):
            return jsonify({"symbols": fallback, "source": "settings"})
        syms = mt5.symbols_get()
        mt5.shutdown()
        if syms:
            names = sorted(s.name for s in syms)
            return jsonify({"symbols": names, "source": "mt5"})
    except Exception:
        pass
    return jsonify({"symbols": fallback, "source": "settings"})


@app.route("/backtest/run", methods=["POST"])
@login_required
def backtest_run():
    import datetime, random, csv as _csv
    import pytz
    UTC = pytz.utc

    data      = request.get_json(force=True)
    symbol    = data.get("symbol", "EURUSD").strip().upper()
    csv_m15   = data.get("csv_m15", "").strip()
    balance   = float(data.get("balance", 10000))
    risk_pct  = float(data.get("risk_pct", 1.0))
    max_trades_override = data.get("max_trades")  # User-specified max trades
    date_from = data.get("date_from", "").strip()
    date_to   = data.get("date_to",   "").strip()

    cfg        = _load_settings()
    tz         = int(cfg.get("timezone_offset", 0))
    ses        = cfg.get("sessions", {})
    tky        = ses.get("tokyo",  {"start": "00:00", "end": "09:00"})
    ldn        = ses.get("london", {"start": "07:00", "end": "16:00"})
    # Use user-specified max_trades if provided, otherwise use settings
    max_trades = int(max_trades_override) if max_trades_override is not None else int(cfg.get("max_trades_per_session", 2))
    tp_mult    = float(cfg.get("tp_multiplier", 10))

    def _parse(t):
        h, m = t.split(":")
        return int(h), int(m)
    def _to_utc(t, off):
        total = t[0]*60 + t[1] - off*60
        total %= 1440
        return total//60, total%60

    tky_s = _to_utc(_parse(tky.get("start","00:00")), tz)
    tky_e = _to_utc(_parse(tky.get("end",  "09:00")), tz)
    ldn_s = _to_utc(_parse(ldn.get("start","07:00")), tz)
    ldn_e = _to_utc(_parse(ldn.get("end",  "16:00")), tz)

    # parse date filter
    dt_from = dt_to = None
    try:
        if date_from:
            dt_from = datetime.datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=UTC)
        if date_to:
            dt_to   = datetime.datetime.strptime(date_to,   "%Y-%m-%d").replace(tzinfo=UTC) + datetime.timedelta(days=1)
    except Exception:
        pass

    def _load_csv(path):
        bars = []
        with open(path, newline="") as f:
            for row in _csv.DictReader(f):
                bars.append({
                    "time":  datetime.datetime.strptime(row["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC),
                    "open":  float(row["open"]),  "high": float(row["high"]),
                    "low":   float(row["low"]),   "close": float(row["close"]),
                })
        return bars

    def _load_mt5(sym, from_dt, to_dt, timeframe_mt5):
        """Fetch real historical data from MT5."""
        try:
            import MetaTrader5 as mt5
            cfg      = _load_settings()
            login    = int(cfg.get("mt5_login", 0))
            password = cfg.get("mt5_password", "")
            server   = cfg.get("mt5_server", "")
            path     = cfg.get("mt5_path", "") or None
            kwargs   = {"login": login, "password": password, "server": server}
            if path:
                kwargs["path"] = path
            if not mt5.initialize(**kwargs):
                return None
            rates = mt5.copy_rates_range(sym, timeframe_mt5, from_dt, to_dt)
            mt5.shutdown()
            if rates is None or len(rates) == 0:
                return None
            bars = []
            for r in rates:
                bars.append({
                    "time":  datetime.datetime.fromtimestamp(r["time"], tz=UTC),
                    "open":  float(r["open"]),
                    "high":  float(r["high"]),
                    "low":   float(r["low"]),
                    "close": float(r["close"]),
                })
            return bars
        except Exception:
            return None

    def _filter(bars):
        if dt_from: bars = [b for b in bars if b["time"] >= dt_from]
        if dt_to:   bars = [b for b in bars if b["time"] <  dt_to]
        return bars

    # Load data: MT5 first (no CSV), then CSV, then synthetic
    bars_m15 = None
    data_source = None
    _from = dt_from or (datetime.datetime.now(UTC) - datetime.timedelta(days=120))
    _to   = dt_to   or  datetime.datetime.now(UTC)
    
    if not csv_m15:
        try:
            import MetaTrader5 as mt5
            bars_m15 = _load_mt5(symbol, _from, _to, mt5.TIMEFRAME_M15)
            if bars_m15 and len(bars_m15) > 0:
                actual_from = bars_m15[0]["time"].strftime("%Y-%m-%d")
                actual_to = bars_m15[-1]["time"].strftime("%Y-%m-%d")
                data_source = f"MT5 real data ({actual_from} to {actual_to})"
        except Exception:
            pass
    if bars_m15 is None and csv_m15:
        bars_m15 = _filter(_load_csv(csv_m15))
        if bars_m15:
            data_source = "CSV data"

    def _make_synthetic(interval_min, start_dt, end_dt):
        """Generate realistic synthetic bars with trends, volatility and session activity."""
        seed = sum(ord(c) for c in symbol) + interval_min
        random.seed(seed)

        # symbol-specific base price and volatility
        sym_upper = symbol.upper()
        if any(x in sym_upper for x in ['XAU','GOLD']):
            base_price, vol_scale = 1950.0, 2.5
        elif any(x in sym_upper for x in ['US30','DJ','DOW']):
            base_price, vol_scale = 38000.0, 80.0
        elif any(x in sym_upper for x in ['NAS','USTEC','US100']):
            base_price, vol_scale = 17000.0, 50.0
        elif any(x in sym_upper for x in ['GBP']):
            base_price, vol_scale = 1.2700, 0.0008
        elif any(x in sym_upper for x in ['JPY']):
            base_price, vol_scale = 149.0, 0.12
        else:  # EURUSD default
            base_price, vol_scale = 1.0850, 0.0006

        result = []
        price  = base_price
        trend  = 0.0
        vol    = vol_scale
        start  = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end    = end_dt.replace(hour=23, minute=59, second=0, microsecond=0)
        days   = (end - start).days + 1
        bars_per_day = (24 * 60) // interval_min

        for i in range(days * bars_per_day):
            dt = start + datetime.timedelta(minutes=interval_min * i)
            h  = dt.hour

            # session volatility multiplier — active during Tokyo/London/NY
            if 0 <= h < 9:    ses_mult = 1.4   # Tokyo
            elif 7 <= h < 16: ses_mult = 1.8   # London
            elif 13 <= h < 22: ses_mult = 1.6  # NY
            else:              ses_mult = 0.5   # dead hours

            # slowly evolving trend + mean reversion
            trend = trend * 0.995 + random.gauss(0, vol_scale * 0.08)
            # volatility clustering
            vol = vol * 0.94 + vol_scale * 0.06 + abs(random.gauss(0, vol_scale * 0.02))

            move  = random.gauss(trend, vol * ses_mult)
            o     = price
            c     = o + move
            wick  = abs(random.gauss(0, vol * ses_mult * 0.6))
            h_bar = max(o, c) + wick
            l_bar = min(o, c) - wick

            # keep price from drifting too far from base (soft mean reversion)
            price = c + (base_price - c) * 0.0005

            result.append({"time": dt, "open": round(o,5), "high": round(h_bar,5),
                           "low": round(l_bar,5), "close": round(price,5)})
        return result

    try:
        sys.path.insert(0, str(ROOT))
        from bor_logic import BORStrategy

        # ── M15 bars only — strategy uses M15 for both levels and signals ──
        if bars_m15 is not None:
            bars = bars_m15
            if not data_source:
                data_source = "MT5 real data"
        else:
            bars = _make_synthetic(15, _from, _to)
            data_source = f"Synthetic demo ({_from.strftime('%Y-%m-%d')} to {_to.strftime('%Y-%m-%d')})"

        if len(bars) < 2:
            return jsonify({"ok": False, "msg": "Not enough bars in the selected date range."}), 400

        bal = balance
        def get_bal(): return bal

        # Per-symbol session tracking
        symbol_session_stats = {
            "tokyo": {"wins": 0, "losses": 0, "trade_count": 0},
            "london": {"wins": 0, "losses": 0, "trade_count": 0}
        }

        strategy = BORStrategy(
            symbol=symbol, risk_pct=risk_pct, account_balance_fn=get_bal,
            max_trades=max_trades, tp_mult=tp_mult,
            tokyo_start=tky_s, tokyo_end=tky_e,
            london_start=ldn_s, london_end=ldn_e,
        )

        trades = []
        for i in range(1, len(bars)):
            bar  = bars[i]
            prev = bars[i - 1]

            sigs = strategy.on_candle(
                utc_dt     = bar["time"],
                high       = bar["high"],  low        = bar["low"],
                close      = bar["close"], prev_close = prev["close"],
                pre_h      = prev["high"], pre_l      = prev["low"],
                open_h     = bar["high"],  open_l     = bar["low"],
            )

            for sig in sigs:
                # Simulate spread buffer logic (same as live bot)
                entry = sig["entry"]
                sl_original = sig["sl"]
                tp = sig["tp"]
                direction = sig["direction"]
                current_close = bar["close"]
                signal_session = sig["session"]
                
                # Check if breakout candle has already covered > 20% of TP distance
                total_tp_distance = abs(tp - entry)
                if direction == "buy":
                    distance_covered = current_close - entry
                else:
                    distance_covered = entry - current_close
                
                tp_coverage_pct = (distance_covered / total_tp_distance * 100) if total_tp_distance > 0 else 0
                
                # Estimate typical spread for symbol
                sym_upper = symbol.upper()
                if any(x in sym_upper for x in ['XAU','GOLD']):
                    typical_spread = 0.50  # $0.50 for gold
                elif any(x in sym_upper for x in ['US30','DJ','DOW']):
                    typical_spread = 3.0   # 3 points for Dow
                elif any(x in sym_upper for x in ['NAS','USTEC','US100']):
                    typical_spread = 2.0   # 2 points for Nasdaq
                elif any(x in sym_upper for x in ['GBP']):
                    typical_spread = 0.00015  # 1.5 pips for GBP pairs
                elif any(x in sym_upper for x in ['JPY']):
                    typical_spread = 0.015    # 1.5 pips for JPY pairs
                else:  # EURUSD default
                    typical_spread = 0.00020  # 2 pips
                
                # Calculate ORIGINAL SL distance from entry
                original_sl_distance = abs(entry - sl_original)
                
                # Only apply spread buffer if SL is dangerously tight (< 2× spread)
                sl_adjusted = sl_original
                if original_sl_distance < (typical_spread * 2):
                    spread_buffer = typical_spread * 1.5
                    if direction == "buy":
                        sl_adjusted = sl_original - spread_buffer
                    else:
                        sl_adjusted = sl_original + spread_buffer
                
                # Decide: immediate entry or wait for retrace
                if tp_coverage_pct > 20:
                    # Breakout covered > 20% of TP → wait for retrace to entry level
                    # BUT cancel if:
                    # 1. Price reaches TP first
                    # 2. Tokyo order: London starts OR Tokyo ends
                    # 3. London order: London ends
                    entry_filled = False
                    order_cancelled = False
                    cancel_reason = ""
                    
                    for j in range(i+1, min(i+50, len(bars))):  # check next 50 bars
                        future_bar = bars[j]
                        future_time = future_bar["time"]
                        
                        # Check session status at this future time
                        future_tky_active = _in_session(future_time.hour * 60 + future_time.minute, tky_s, tky_e)
                        future_ldn_active = _in_session(future_time.hour * 60 + future_time.minute, ldn_s, ldn_e)
                        
                        # Check if order should be cancelled due to session end
                        if signal_session == "tokyo":
                            # Tokyo orders: cancel if London starts OR Tokyo ends
                            if future_ldn_active:
                                order_cancelled = True
                                cancel_reason = "London session started"
                                break
                            elif not future_tky_active:
                                order_cancelled = True
                                cancel_reason = "Tokyo session ended"
                                break
                        elif signal_session == "london":
                            # London orders: cancel if London ends
                            if not future_ldn_active:
                                order_cancelled = True
                                cancel_reason = "London session ended"
                                break
                        
                        # Check if TP reached first
                        if direction == "buy":
                            if future_bar["high"] >= tp:
                                order_cancelled = True
                                cancel_reason = "price reached TP"
                                break
                            # Check if price retraced to entry
                            if future_bar["low"] <= entry:
                                entry_filled = True
                                entry_bar_idx = j
                                break
                        else:
                            if future_bar["low"] <= tp:
                                order_cancelled = True
                                cancel_reason = "price reached TP"
                                break
                            # Check if price retraced to entry
                            if future_bar["high"] >= entry:
                                entry_filled = True
                                entry_bar_idx = j
                                break
                    
                    if order_cancelled:
                        # Order cancelled → skip trade
                        continue
                    
                    if not entry_filled:
                        # Price never retraced and order not cancelled → expired, skip trade
                        continue
                    
                    # Simulate trade from retrace entry point
                    outcome, _, _ = _sim_trade(bars, entry_bar_idx, direction, tp, sl_adjusted)
                else:
                    # Breakout covered ≤ 20% of TP → enter immediately
                    outcome, _, _ = _sim_trade(bars, i, direction, tp, sl_adjusted)
                
                risk_usd = balance * risk_pct / 100.0
                pnl = risk_usd * tp_mult if outcome == "tp" else -risk_usd
                bal += pnl
                
                # Update per-symbol session stats
                session_name = sig["session"]
                if outcome == "tp":
                    symbol_session_stats[session_name]["wins"] += 1
                elif outcome == "sl":
                    symbol_session_stats[session_name]["losses"] += 1
                symbol_session_stats[session_name]["trade_count"] += 1
                
                trades.append({
                    "time":      sig["time"].strftime("%Y-%m-%d %H:%M"),
                    "session":   session_name,
                    "direction": direction,
                    "entry":     round(entry, 5),
                    "sl":        round(sl_adjusted, 5),
                    "tp":        round(tp, 5),
                    "outcome":   outcome,
                    "pnl":       round(pnl, 2),
                    "balance":   round(bal, 2),
                    "tp_coverage": round(tp_coverage_pct, 1),
                    "entry_type": "LIMIT" if tp_coverage_pct > 20 else "MARKET",
                })

        wins   = sum(1 for t in trades if t["outcome"] == "tp")
        losses = sum(1 for t in trades if t["outcome"] == "sl")
        total  = wins + losses

        sessions_result = {}
        for ses_name in ("tokyo", "london"):
            st  = [t for t in trades if t["session"] == ses_name]
            sw  = sum(1 for t in st if t["outcome"] == "tp")
            sl2 = sum(1 for t in st if t["outcome"] == "sl")
            sessions_result[ses_name] = {
                "wins": sw, "losses": sl2, "total": sw+sl2,
                "win_rate": round(sw/(sw+sl2)*100, 1) if (sw+sl2) else 0,
                "pnl": round(sum(t["pnl"] for t in st), 2),
            }

        actual = _actual_win_rate(symbol)

        date_range = ""
        if bars:
            date_range = f"{bars[0]['time'].strftime('%Y-%m-%d')} → {bars[-1]['time'].strftime('%Y-%m-%d')}"

        result = {
            "symbol":      symbol,
            "data_source": data_source,
            "date_range":  date_range,
            "timeframe":   "M15",
            "initial":     balance,
            "final":       round(bal, 2),
            "net_pnl":     round(bal - balance, 2),
            "net_pct":     round((bal - balance) / balance * 100, 2),
            "total":       total,
            "wins":        wins,
            "losses":      losses,
            "win_rate":    round(wins/total*100, 1) if total else 0,
            "sessions":    sessions_result,
            "trades":      trades[-50:],
            "actual":      actual,
            "run_at":      datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }

        try:
            existing = json.loads(BACKTEST_FILE.read_text()) if BACKTEST_FILE.exists() else {}
        except Exception:
            existing = {}
        existing[symbol] = result
        BACKTEST_FILE.write_text(json.dumps(existing, indent=2))

        return jsonify({"ok": True, "result": result})

    except Exception as e:
        import traceback
        return jsonify({"ok": False, "msg": str(e), "trace": traceback.format_exc()}), 500


def _sim_trade(bars, entry_idx, direction, tp, sl):
    for j in range(entry_idx+1, len(bars)):
        b = bars[j]
        if direction == "buy":
            if b["high"] >= tp: return "tp", tp, b["time"]
            if b["low"]  <= sl: return "sl", sl, b["time"]
        else:
            if b["low"]  <= tp: return "tp", tp, b["time"]
            if b["high"] >= sl: return "sl", sl, b["time"]
    return "open", bars[-1]["close"], bars[-1]["time"]


def _actual_win_rate(symbol: str) -> dict:
    """Compute win rate from live trade history in bor_state.json for a symbol."""
    try:
        s = json.loads(STATE_FILE.read_text())
        hist = [t for t in s.get("trade_history", []) if t.get("symbol") == symbol]
        wins   = sum(1 for t in hist if t.get("close_reason") == "closed")
        losses = sum(1 for t in hist if t.get("close_reason") == "sl")
        total  = wins + losses
        return {"wins": wins, "losses": losses, "total": total,
                "win_rate": round(wins/total*100, 1) if total else None}
    except Exception:
        return {"wins": 0, "losses": 0, "total": 0, "win_rate": None}


@app.route("/backtest/results")
@login_required
def backtest_results():
    try:
        return jsonify(json.loads(BACKTEST_FILE.read_text()) if BACKTEST_FILE.exists() else {})
    except Exception:
        return jsonify({})


# ── launch ────────────────────────────────────────────────────────────────────

def _open_browser():
    webbrowser.open("http://localhost:5000")

if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(debug=False, port=5000)
