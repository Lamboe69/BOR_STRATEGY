"""
dashboard.py — BOR Strategy web dashboard (Flask).
Serves the live dashboard + settings page.
Manages the live bot as a subprocess.

Run:
    python ui/dashboard.py
"""

import json, sys, subprocess, signal, os, hashlib, secrets, datetime
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
    if _bot_process is not None and _bot_process.poll() is None:
        return True
    # Also check if any live_bot process is running (started externally)
    try:
        import subprocess
        r = subprocess.run(["pgrep", "-f", "live_bot.py"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and len(r.stdout.strip()) > 0
    except Exception:
        return False

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

def api_login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"ok": False, "msg": "Authentication required"}), 401
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
@api_login_required
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

    # ── computed stats ──────────────────────────────────────────
    import datetime as _dt_mod

    cfg_settings = _load_settings()
    initial_bal = float(cfg_settings.get("initial_balance", 10000))
    risk_pct    = float(cfg_settings.get("risk_pct", 1.0))
    s["initial_balance"] = initial_bal
    s["risk_pct"] = risk_pct

    today_str = _dt_mod.datetime.now(_dt_mod.timezone.utc).strftime("%Y-%m-%d")
    hist = s.get("trade_history", [])
    open_trds = s.get("open_trades", [])

    # Daily stats
    today_trades = [
        t for t in hist
        if t.get("closed_at", "").startswith(today_str)
    ]
    daily_wins   = sum(1 for t in today_trades if t.get("actual_pnl", 0) > 0)
    daily_losses = sum(1 for t in today_trades if t.get("actual_pnl", 0) < 0)
    daily_pnl    = sum(t.get("actual_pnl", 0) for t in today_trades)
    s["daily_stats"] = {
        "trades": len(today_trades),
        "wins":   daily_wins,
        "losses": daily_losses,
        "win_rate": round(daily_wins / (daily_wins + daily_losses) * 100, 1)
            if (daily_wins + daily_losses) > 0 else None,
        "pnl": round(daily_pnl, 2),
    }

    # Symbol stats (all-time from trade history)
    sym_stats = {}
    for t in hist:
        raw = t.get("symbol", "")
        # strip broker suffix for cleaner display
        clean = raw.rstrip("mM.-").upper()
        if clean not in sym_stats:
            sym_stats[clean] = {"wins": 0, "losses": 0, "pnl": 0}
        pnl = t.get("actual_pnl", 0)
        if pnl > 0:
            sym_stats[clean]["wins"] += 1
        elif pnl < 0:
            sym_stats[clean]["losses"] += 1
        sym_stats[clean]["pnl"] = round(sym_stats[clean]["pnl"] + pnl, 2)
    s["symbol_stats"] = sym_stats

    # Exposure — total $ at risk in open trades
    exposure = 0.0
    for t in open_trds:
        entry = t.get("entry", 0)
        sl    = t.get("sl", 0)
        lot   = t.get("lot", 0)
        dist  = abs(entry - sl)
        # rough approximation: 1 pip = 0.0001 for 5-digit forex, 0.01 for XAU, 0.1 for indices
        # using a per-symbol pip value would require symbol info, so use settings risk %
        exposure += initial_bal * risk_pct / 100.0
    s["exposure"] = round(exposure, 2)

    # Running balance on each history trade
    cumulative = initial_bal
    for t in hist:
        cumulative += t.get("actual_pnl", 0)
        t["balance"] = round(cumulative, 2)

    return jsonify(s)


@app.route("/performance")
@api_login_required
def performance():
    """Return performance statistics including trade stats, session breakdown, symbol summary"""
    try:
        sys.path.insert(0, str(ROOT))
        from performance_tracker import get_stats as get_curve_stats
        from trades_db import TradesDB

        result = get_curve_stats()

        # Use settings initial_balance for consistency across pages
        try:
            cfg = _load_settings()
            result["initial_balance"] = float(cfg.get("initial_balance", result["initial_balance"]))
        except Exception:
            pass

        # Enrich with trade stats from database
        trades_db = TradesDB(ROOT / "bor_trades.db.json")
        all_closed = trades_db.get_closed_trades(limit=1000)
        session_stats = trades_db.get_session_stats()

        # Overall trade stats
        total = len(all_closed)
        wins  = sum(1 for t in all_closed if t.get("actual_pnl", 0) > 0)
        loss  = sum(1 for t in all_closed if t.get("actual_pnl", 0) < 0)
        pnl   = sum(t.get("actual_pnl", 0) for t in all_closed)

        result["total_trades"] = total
        result["wins"]   = wins
        result["losses"] = loss
        result["win_rate"] = round(wins / (wins + loss) * 100, 1) if (wins + loss) else 0

        # Session breakdown
        ses_summary = {}
        for sym, ses_data in session_stats.items():
            for ses_name, st in ses_data.items():
                if ses_name not in ses_summary:
                    ses_summary[ses_name] = {"wins": 0, "losses": 0, "trade_count": 0}
                ses_summary[ses_name]["wins"] += st.get("wins", 0)
                ses_summary[ses_name]["losses"] += st.get("losses", 0)
                ses_summary[ses_name]["trade_count"] += st.get("trade_count", 0)
        # Fill missing sessions
        for sn in ("tokyo", "london"):
            if sn not in ses_summary:
                ses_summary[sn] = {"wins": 0, "losses": 0, "trade_count": 0}
            sw = ses_summary[sn]["wins"]
            sl = ses_summary[sn]["losses"]
            ses_summary[sn]["win_rate"] = round(sw / (sw + sl) * 100, 1) if (sw + sl) else 0
        result["session_summary"] = ses_summary

        # Symbol summary table
        sym_summary = {}
        for t in all_closed:
            raw = t.get("symbol", "")
            clean = raw.rstrip("mM.-").upper()
            if clean not in sym_summary:
                sym_summary[clean] = {"wins": 0, "losses": 0, "pnl": 0, "trades": 0}
            p = t.get("actual_pnl", 0)
            if p > 0:
                sym_summary[clean]["wins"] += 1
            elif p < 0:
                sym_summary[clean]["losses"] += 1
            sym_summary[clean]["pnl"] = round(sym_summary[clean]["pnl"] + p, 2)
            sym_summary[clean]["trades"] += 1
        for _, v in sym_summary.items():
            tot = v["wins"] + v["losses"]
            v["win_rate"] = round(v["wins"] / tot * 100, 1) if tot else 0
        result["symbol_summary"] = sym_summary

        # Recent trade history (last 50)
        recent = all_closed[-50:][::-1]  # newest first
        for t in recent:
            if "balance" not in t:
                t.pop("balance", None)
        result["recent_trades"] = recent

        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/performance/symbol/<symbol>")
@api_login_required
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
        # Use start_bot.sh wrapper which properly detaches with nohup
        subprocess.run(
            ["bash", str(ROOT / "start_bot.sh")],
            cwd=str(ROOT), timeout=10
        )
        # Re-read bot process PID
        r = subprocess.run(["pgrep", "-f", "live_bot.py"], capture_output=True, text=True, timeout=5)
        pid = int(r.stdout.strip().split()[0]) if r.returncode == 0 else None
        # Mark state as running
        try:
            s = json.loads(STATE_FILE.read_text())
            s["bot_running"] = True
            STATE_FILE.write_text(json.dumps(s, indent=2))
        except Exception:
            pass
        return jsonify({"ok": True, "pid": pid})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/bot/config", methods=["GET", "POST"])
@admin_required
def bot_config():
    """Get or update bot configuration."""
    if request.method == "GET":
        cfg = _load_settings()
        return jsonify({"ok": True, "config": cfg})
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"ok": False, "msg": "No data provided"}), 400
        # Validate and update
        cfg = _load_settings()
        for key in ("symbols", "risk_pct", "max_trades_per_session", "tp_multiplier",
                     "poll_interval", "timezone_offset", "initial_balance",
                     "min_range_points"):
            if key in data:
                cfg[key] = data[key]
        if "sessions" in data:
            cfg["sessions"] = data["sessions"]
        if "risk_management" in data:
            cfg["risk_management"] = data["risk_management"]
        if "h1_trend_filter" in data:
            cfg["h1_trend_filter"] = data["h1_trend_filter"]
        if "telegram" in data:
            cfg["telegram"] = data["telegram"]
        if "symbols_config" in data:
            cfg["symbols_config"] = data["symbols_config"]
        if "retracement" in data:
            cfg["retracement"] = data["retracement"]
        SETTINGS_FILE.write_text(json.dumps(cfg))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/bot/webhook", methods=["POST"])
@api_login_required
def bot_webhook():
    """Generic webhook endpoint for external integrations."""
    data = request.get_json(force=True) if request.is_json else {}
    action = data.get("action", "")
    if action == "ping":
        return jsonify({"ok": True, "msg": "pong"})
    if action == "stop":
        return bot_stop()
    if action == "start":
        return bot_start()
    return jsonify({"ok": False, "msg": f"Unknown action: {action}"}), 400


@app.route("/bot/daily")
@api_login_required
def bot_daily_stats():
    """Return daily P&L breakdown."""
    try:
        import trades_db
        db = trades_db.TradesDB(ROOT / "bor_trades.db.json")
        closed = db.get_closed_trades()
        days = {}
        for t in closed:
            day = t.get("closed_at", "")[:10]
            if not day:
                continue
            if day not in days:
                days[day] = {"date": day, "trades": 0, "wins": 0,
                             "losses": 0, "pnl": 0.0}
            days[day]["trades"] += 1
            if t.get("close_reason") == "tp":
                days[day]["wins"] += 1
            elif t.get("close_reason") == "sl":
                days[day]["losses"] += 1
            days[day]["pnl"] += t.get("actual_pnl", 0)
        result = sorted(days.values(), key=lambda x: x["date"])
        return jsonify({"ok": True, "daily": result})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/bot/telegram-test", methods=["POST"])
@api_login_required
def bot_telegram_test():
    """Send a test Telegram message."""
    try:
        sys.path.insert(0, str(ROOT))
        from python_mt5.alerts import send_telegram
        ok = send_telegram("🧪 <b>BOR Bot Test</b>\nYour Telegram alert system is working!")
        if ok:
            return jsonify({"ok": True})
        return jsonify({"ok": False, "msg": "Telegram not configured. Check settings."}), 400
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/state/risk")
@api_login_required
def state_risk():
    """Return risk management state."""
    try:
        import trades_db
        db = trades_db.TradesDB(ROOT / "bor_trades.db.json")
        risk_stats = db.get_risk_stats()
        return jsonify({"ok": True, "risk": risk_stats})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/bot/stop", methods=["POST"])
@admin_required
def bot_stop():
    global _bot_process
    if not _bot_running():
        return jsonify({"ok": True, "msg": "not running"})
    # Kill by _bot_process if tracked
    if _bot_process is not None:
        try:
            _bot_process.terminate()
            _bot_process.wait(timeout=5)
        except Exception:
            try:
                _bot_process.kill()
            except Exception:
                pass
        _bot_process = None
    # Also kill any live_bot.py process regardless of how it was started
    try:
        subprocess.run(["pkill", "-f", "live_bot.py"], timeout=5)
    except Exception:
        pass
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
@api_login_required
def backtest_symbols():
    """Return available symbols from MT5 if reachable, else fall back to settings."""
    cfg = _load_settings()
    fallback = cfg.get("symbols", ["EURUSD", "XAUUSD", "US30", "USTEC"])
    try:
        import MetaTrader5 as mt5
        login    = int(cfg.get("mt5_login", 0))
        password = cfg.get("mt5_password", "")
        server   = cfg.get("mt5_server", "")
        kwargs   = {"login": login, "password": password, "server": server}
        if not mt5.initialize(**kwargs):
            return jsonify({"symbols": fallback, "source": "settings"})
        syms = mt5.symbols_get()
        if syms:
            names = sorted(s.name for s in syms)
            return jsonify({"symbols": names, "source": "mt5"})
    except Exception:
        pass
    return jsonify({"symbols": fallback, "source": "settings"})


@app.route("/backtest/run", methods=["POST"])
@api_login_required
def backtest_run():
    import datetime
    import pytz
    UTC = pytz.utc

    data      = request.get_json(force=True)
    symbol    = data.get("symbol", "EURUSD").strip()
    balance   = float(data.get("balance", 10000))
    risk_pct  = float(data.get("risk_pct", 1.0))
    max_trades_override = data.get("max_trades")
    date_from = data.get("date_from", "").strip()
    date_to   = data.get("date_to",   "").strip()

    cfg        = _load_settings()
    tz         = int(cfg.get("timezone_offset", 0))
    ses        = cfg.get("sessions", {})
    tky        = ses.get("tokyo",  {"start": "00:00", "end": "09:00"})
    ldn        = ses.get("london", {"start": "07:00", "end": "16:00"})
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

    dt_from = dt_to = None
    try:
        if date_from:
            dt_from = datetime.datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=UTC)
        if date_to:
            dt_to   = datetime.datetime.strptime(date_to,   "%Y-%m-%d").replace(tzinfo=UTC) + datetime.timedelta(days=1)
        if dt_from and dt_to and dt_from >= dt_to:
            return jsonify({"ok": False, "msg": "Start date must be before end date"}), 400
    except ValueError as e:
        return jsonify({"ok": False, "msg": f"Invalid date format: {str(e)}"}), 400
    except Exception:
        pass

    def _resolve_mt5_symbol(sym):
        """Resolve broker symbol name (e.g. EURUSD -> EURUSDm for Exness)."""
        import MetaTrader5 as mt5
        info = mt5.symbol_info(sym)
        if info is not None:
            return sym
        candidates = [sym + s for s in ('m', '.m', '-M', '') if sym + s != sym]
        for c in candidates:
            if mt5.symbol_info(c) is not None:
                return c
        return sym

    def _load_mt5_chunk(resolved, from_dt, to_dt, timeframe_mt5):
        """Fetch a single chunk of MT5 data."""
        rates = mt5.copy_rates_range(resolved, timeframe_mt5, from_dt, to_dt)
        if rates is None or len(rates) == 0:
            return []
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

    def _load_mt5_all(sym, from_dt, to_dt, timeframe_mt5, max_candles=80000):
        """Fetch data, auto-chunking if requested range is too large."""
        cfg      = _load_settings()
        login    = int(cfg.get("mt5_login", 0))
        password = cfg.get("mt5_password", "")
        server   = cfg.get("mt5_server", "")
        kwargs   = {"login": login, "password": password, "server": server}

        if not mt5.initialize(**kwargs):
            error = mt5.last_error()
            return None, f"MT5 initialization failed: {error}"

        resolved = _resolve_mt5_symbol(sym)
        info = mt5.symbol_info(resolved)
        if info is None:
            all_syms = mt5.symbols_get()
            similar = []
            if all_syms:
                base = sym.replace('M', '').replace('m', '')
                similar = [s.name for s in all_syms if base.lower() in s.name.lower()][:5]
            if similar:
                return None, f"Symbol '{sym}' not found. Did you mean: {', '.join(similar)}?"
            return None, f"Symbol '{sym}' not found in MT5."

        if not info.visible:
            mt5.symbol_select(resolved, True)

        total_days = (to_dt - from_dt).days
        estimated_candles = total_days * 96  # M15 = 96 candles/day

        if estimated_candles <= max_candles:
            bars = _load_mt5_chunk(resolved, from_dt, to_dt, timeframe_mt5)
            if not bars:
                return None, f"No data for '{resolved}' in {from_dt.strftime('%Y-%m-%d')} to {to_dt.strftime('%Y-%m-%d')}."
            return bars, resolved

        # Split into yearly chunks
        all_bars = []
        chunk_start = from_dt
        while chunk_start < to_dt:
            chunk_end = min(chunk_start + datetime.timedelta(days=365), to_dt)
            chunk_bars = _load_mt5_chunk(resolved, chunk_start, chunk_end, timeframe_mt5)
            if chunk_bars:
                all_bars.extend(chunk_bars)
            chunk_start = chunk_end

        if not all_bars:
            return None, f"No data for '{resolved}' in {from_dt.strftime('%Y-%m-%d')} to {to_dt.strftime('%Y-%m-%d')}."

        # Deduplicate by time
        seen = set()
        deduped = []
        for b in all_bars:
            t = b["time"].timestamp()
            if t not in seen:
                seen.add(t)
                deduped.append(b)
        deduped.sort(key=lambda b: b["time"])

        return deduped, resolved

    bars_m15 = None
    data_source = None
    _from = dt_from or (datetime.datetime.now(UTC) - datetime.timedelta(days=120))
    _to   = dt_to   or  datetime.datetime.now(UTC)

    import MetaTrader5 as mt5
    bars_m15, err_or_sym = _load_mt5_all(symbol, _from, _to, mt5.TIMEFRAME_M15)
    if bars_m15 is not None and len(bars_m15) > 0:
        resolved_sym = err_or_sym
        actual_from = bars_m15[0]["time"].strftime("%Y-%m-%d")
        actual_to = bars_m15[-1]["time"].strftime("%Y-%m-%d")
        data_source = f"MT5 real data for {resolved_sym} ({actual_from} to {actual_to})"
    else:
        return jsonify({"ok": False, "msg": err_or_sym}), 400

    try:
        sys.path.insert(0, str(ROOT))
        from bor_logic import BORStrategy

        # Use real data from MT5 or CSV
        bars = bars_m15

        if len(bars) < 2:
            return jsonify({"ok": False, "msg": "Not enough bars in the selected date range."}), 400

        bal = balance
        def get_bal(): return bal

        # Per-symbol config (strip broker suffixes like 'm', '.m', '-M')
        sym_base = symbol.upper()
        for sfx in ('M', '.M', '-M'):
            if sym_base.endswith(sfx):
                sym_base = sym_base[:-len(sfx)]
                break
        sym_cfg = cfg.get("symbols_config", {}).get(sym_base, {})
        bt_tp_mult = float(sym_cfg.get("tp_multiplier", tp_mult))
        bt_min_range = float(sym_cfg.get("min_range_points", float(cfg.get("min_range_points", 0))))
        bt_min_stop_points = int(sym_cfg.get("min_stop_points", 0))
        # Infer point size for min_stop_distance
        _ps = {'XAU': 0.001, 'XAG': 0.001, 'US30': 0.01, 'USTEC': 0.01, 'NAS': 0.01, 'DOW': 0.01, 'JPY': 0.001}
        bt_min_stop_dist = bt_min_stop_points * next((v for k, v in _ps.items() if k in symbol.upper()), 0.00001)

        recfg = cfg.get("retracement", {})
        bt_retrace = bool(recfg.get("enabled", True))
        bt_retrace_bars = int(recfg.get("max_wait_bars", 50))
        bt_retrace_thresh = float(recfg.get("coverage_threshold", 0.0))

        # Per-symbol session tracking
        symbol_session_stats = {
            "tokyo": {"wins": 0, "losses": 0, "trade_count": 0},
            "london": {"wins": 0, "losses": 0, "trade_count": 0}
        }

        strategy = BORStrategy(
            symbol=symbol, risk_pct=risk_pct, account_balance_fn=get_bal,
            max_trades=max_trades, tp_mult=bt_tp_mult,
            tokyo_start=tky_s, tokyo_end=tky_e,
            london_start=ldn_s, london_end=ldn_e,
            min_range_points=bt_min_range,
            min_stop_distance=bt_min_stop_dist,
            retrace_enabled=bt_retrace,
            retrace_max_bars=bt_retrace_bars,
            retrace_coverage_threshold=bt_retrace_thresh,
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
                entry = sig["entry"]
                sl = sig["sl"]
                tp = sig["tp"]
                direction = sig["direction"]
                

                # Estimate typical spread for symbol
                sym_upper = symbol.upper()
                if any(x in sym_upper for x in ['XAU','GOLD']):
                    typical_spread = 0.50
                elif any(x in sym_upper for x in ['US30','DJ','DOW']):
                    typical_spread = 3.0
                elif any(x in sym_upper for x in ['NAS','USTEC','US100']):
                    typical_spread = 2.0
                elif any(x in sym_upper for x in ['GBP']):
                    typical_spread = 0.00015
                elif any(x in sym_upper for x in ['JPY']):
                    typical_spread = 0.015
                else:
                    typical_spread = 0.00020
                
                original_sl_distance = abs(entry - sl)
                sl_adjusted = sl
                if original_sl_distance < (typical_spread * 2):
                    spread_buffer = typical_spread * 1.5
                    if direction == "buy":
                        sl_adjusted = sl - spread_buffer
                    else:
                        sl_adjusted = sl + spread_buffer
                
                # Simulate trade from entry bar
                outcome, _, _ = _sim_trade(bars, i, direction, tp, sl_adjusted)
                
                risk_usd = balance * risk_pct / 100.0
                pnl = risk_usd * bt_tp_mult if outcome == "tp" else -risk_usd
                bal += pnl
                
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
                    "sl":        round(sl, 5),
                    "tp":        round(tp, 5),
                    "outcome":   outcome,
                    "pnl":       round(pnl, 2),
                    "balance":   round(bal, 2),
                    "tp_coverage": 0.0,
                    "entry_type": sig.get("entry_type", "MARKET"),
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

        # Compute derived metrics
        win_trades  = [t for t in trades if t["outcome"] == "tp"]
        loss_trades = [t for t in trades if t["outcome"] == "sl"]
        avg_win     = round(sum(t["pnl"] for t in win_trades) / len(win_trades), 2) if win_trades else 0
        avg_loss    = round(sum(t["pnl"] for t in loss_trades) / len(loss_trades), 2) if loss_trades else 0
        largest_win = round(max(t["pnl"] for t in win_trades), 2) if win_trades else 0
        largest_loss = round(min(t["pnl"] for t in loss_trades), 2) if loss_trades else 0

        # Equity curve data points (balance after each trade)
        eq_curve = [{"time": t["time"], "balance": t["balance"]} for t in trades]

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
            "avg_win":     avg_win,
            "avg_loss":    avg_loss,
            "largest_win": largest_win,
            "largest_loss": largest_loss,
            "avg_rr":      round(avg_win / abs(avg_loss), 2) if avg_loss else 0,
            "eq_curve":    eq_curve,
            "sessions":    sessions_result,
            "trades":      trades[-50:],
            "actual":      actual,
            "run_at":      datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "config": {
                "tp_multiplier": bt_tp_mult,
                "min_range_points": bt_min_range,
                "retrace_enabled": bt_retrace,
                "retrace_max_bars": bt_retrace_bars,
                "retrace_coverage_threshold": bt_retrace_thresh,
            },
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
        wins   = sum(1 for t in hist if t.get("close_reason") == "tp")
        losses = sum(1 for t in hist if t.get("close_reason") == "sl")
        total  = wins + losses
        return {"wins": wins, "losses": losses, "total": total,
                "win_rate": round(wins/total*100, 1) if total else None}
    except Exception:
        return {"wins": 0, "losses": 0, "total": 0, "win_rate": None}


@app.route("/backtest/results")
@api_login_required
def backtest_results():
    try:
        return jsonify(json.loads(BACKTEST_FILE.read_text()) if BACKTEST_FILE.exists() else {})
    except Exception:
        return jsonify({})


# ── launch ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=False, port=5000)
