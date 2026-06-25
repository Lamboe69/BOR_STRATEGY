"""
alerts.py — Notification system for the BOR bot.
Supports Telegram bot notifications for trade events, errors, and daily P&L.
"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("BOR-Alerts")

ROOT = Path(__file__).resolve().parent.parent
SETTINGS_FILE = ROOT / "bor_settings.json"


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except Exception:
        return {}


def _tg_config() -> dict:
    cfg = _load_settings().get("telegram", {})
    return cfg


def send_telegram(msg: str) -> bool:
    cfg = _tg_config()
    if not cfg.get("enabled") or not cfg.get("bot_token") or not cfg.get("chat_id"):
        return False
    try:
        import requests
        url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": cfg["chat_id"],
            "text": msg,
            "parse_mode": "HTML",
        }, timeout=10)
        ok = resp.status_code == 200
        if not ok:
            log.warning("Telegram send failed: %s", resp.text)
        return ok
    except Exception as exc:
        log.warning("Telegram error: %s", exc)
        return False


def notify_trade(symbol: str, direction: str, session: str,
                 entry: float, sl: float, tp: float, lot: float,
                 ticket: int, order_type: str):
    emoji = "🟢" if direction == "buy" else "🔴"
    send_telegram(
        f"{emoji} <b>New Trade</b>\n"
        f"Symbol: {symbol}\n"
        f"Direction: {direction.upper()}\n"
        f"Session: {session.title()}\n"
        f"Type: {order_type}\n"
        f"Entry: {entry:.5f}\n"
        f"SL: {sl:.5f}\n"
        f"TP: {tp:.5f}\n"
        f"Lot: {lot:.2f}\n"
        f"Ticket: #{ticket}"
    )


def notify_close(symbol: str, direction: str, session: str,
                 entry: float, close_price: float, pnl: float,
                 reason: str, ticket: int):
    emoji = "✅" if pnl >= 0 else "❌"
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    send_telegram(
        f"{emoji} <b>Trade Closed</b>\n"
        f"Symbol: {symbol}\n"
        f"Direction: {direction.upper()}\n"
        f"Session: {session.title()}\n"
        f"Entry: {entry:.5f}\n"
        f"Close: {close_price:.5f}\n"
        f"P&L: {pnl_str}\n"
        f"Reason: {reason}\n"
        f"Ticket: #{ticket}"
    )


def notify_error(msg: str):
    send_telegram(f"⚠️ <b>Bot Error</b>\n{msg}")


def notify_daily_pnl(date_str: str, pnl: float, total_trades: int,
                     wins: int, losses: int, balance: float):
    emoji = "📈" if pnl >= 0 else "📉"
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    win_rate = round(wins / (wins + losses) * 100, 1) if (wins + losses) else 0
    send_telegram(
        f"{emoji} <b>Daily P&L — {date_str}</b>\n"
        f"P&L: {pnl_str}\n"
        f"Trades: {total_trades}\n"
        f"Win Rate: {win_rate}% ({wins}W/{losses}L)\n"
        f"Balance: ${balance:.2f}"
    )


def notify_risk_pause(reason: str):
    send_telegram(f"⏸️ <b>Risk Pause</b>\n{reason}")


def notify_daily_reset(pnl: float, balance: float):
    send_telegram(
        f"🔄 <b>Daily Reset</b>\n"
        f"Previous day P&L: ${pnl:+.2f}\n"
        f"Current balance: ${balance:.2f}"
    )
