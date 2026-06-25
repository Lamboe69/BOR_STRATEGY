"""
MetaTrader5.py — Shim that proxies the MetaTrader5 Python API to an MT5
terminal running under Wine via the mt5linux RPyC bridge.

All functions and constants of the original MetaTrader5 module are
re-exported so that existing code can simply ``import MetaTrader5 as mt5``
without any source-level changes.
"""

from __future__ import annotations

import functools
import sys

import mt5linux

_MT5_CLASS = mt5linux.MetaTrader5
_inst: _MT5_CLASS | None = None


def _get_inst():
    global _inst
    if _inst is None:
        import os
        host = os.environ.get("MT5_HOST", "127.0.0.1")
        port = int(os.environ.get("MT5_PORT", "18812"))
        timeout = int(os.environ.get("MT5_TIMEOUT", "30"))
        try:
            _inst = _MT5_CLASS(host=host, port=port, timeout=timeout)
        except Exception as exc:
            raise RuntimeError(
                f"Cannot connect to MT5 bridge at {host}:{port}. "
                f"Is the mt5linux server running in Wine? ({exc})"
            ) from exc
    return _inst


# ── helpers ────────────────────────────────────────────────────────────

def _proxy_method(name):
    """Return a module-level function that delegates to the singleton."""

    @functools.wraps(getattr(_MT5_CLASS, name))
    def _wrapper(*args, **kwargs):
        return getattr(_get_inst(), name)(*args, **kwargs)
    return _wrapper


# ── export all constants (class attributes) ────────────────────────────

_skip = {
    '__class__', '__del__', '__delattr__', '__dict__', '__dir__',
    '__doc__', '__eq__', '__firstlineno__', '__format__', '__ge__',
    '__getattribute__', '__getstate__', '__gt__', '__hash__', '__init__',
    '__init_subclass__', '__le__', '__lt__', '__module__', '__ne__',
    '__new__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__',
    '__sizeof__', '__static_attributes__', '__str__', '__subclasshook__',
    '__weakref__', '__wrapped__',
    # method names — handled separately below
    'account_info', 'copy_rates_from', 'copy_rates_from_pos',
    'copy_rates_range', 'copy_ticks_from', 'copy_ticks_range',
    'eval', 'execute', 'history_deals_get', 'history_deals_total',
    'history_orders_get', 'history_orders_total', 'initialize', 'last_error',
    'login', 'market_book_add', 'market_book_get', 'market_book_release',
    'order_calc_margin', 'order_calc_profit', 'order_check', 'order_send',
    'orders_get', 'orders_total', 'positions_get', 'positions_total',
    'shutdown', 'symbol_info', 'symbol_info_tick', 'symbol_select',
    'symbols_get', 'symbols_total', 'terminal_info', 'version',
}

for _attr in dir(_MT5_CLASS):
    if _attr.startswith('_') or _attr in _skip:
        continue
    _val = getattr(_MT5_CLASS, _attr)
    if not callable(_val):
        setattr(sys.modules[__name__], _attr, _val)


# ── export all public instance methods as module-level functions ───────

# fmt: off
__all__ = [
    'initialize', 'shutdown', 'login', 'account_info', 'last_error',
    'version', 'terminal_info',
    'symbol_info', 'symbol_info_tick', 'symbol_select', 'symbols_get',
    'symbols_total',
    'copy_rates_from', 'copy_rates_from_pos', 'copy_rates_range',
    'copy_ticks_from', 'copy_ticks_range',
    'positions_get', 'positions_total', 'orders_get', 'orders_total',
    'order_send', 'order_check',
    'history_deals_get', 'history_deals_total', 'history_orders_get',
    'history_orders_total',
    'market_book_add', 'market_book_get', 'market_book_release',
    'order_calc_margin', 'order_calc_profit',
    'eval', 'execute',
]

for _name in __all__:
    setattr(sys.modules[__name__], _name, _proxy_method(_name))
