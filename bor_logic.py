"""
bor_logic.py — Pure BOR strategy logic, faithful to the LuxAlgo Pine Script.

Level snapshotting  : 15-min chart — pre_high/pre_low (last closed 15-min candle
                      before session) and open_high/open_low (first 15-min candle
                      of the session). Sorted high→low: S1 > S2 > S3 > S4.

Signal detection    : 5-min chart — buy when 5-min candle closes above S1,
                      sell when 5-min candle closes below S4.

Entry / SL / TP:
  Buy  — entry=S1, SL=S2, TP=entry+(entry-SL)*10
  Sell — entry=S4, SL=S3, TP=entry-(SL-entry)*10

Session rules:
  - One trade active at a time globally across all sessions
  - Max max_trades signals per session
  - Stop all signals once a WIN is recorded in that session
  - Wick-out filter: after a wick-out loss, next signal in the same direction
    requires the 5-min breakout candle to CLOSE beyond the previous entry
"""

from dataclasses import dataclass, field
from typing import Optional
import datetime
import math


# ── helpers ───────────────────────────────────────────────────────────────────

def sort4(a, b, c, d):
    """Return (s1, s2, s3, s4) sorted high → low."""
    vals = sorted([a, b, c, d], reverse=True)
    return tuple(vals)


def in_session(utc_dt: datetime.datetime, start: tuple, end: tuple) -> bool:
    """True if utc_dt falls inside [start, end) (hour, minute) UTC."""
    t = utc_dt.hour * 60 + utc_dt.minute
    s = start[0] * 60 + start[1]
    e = end[0]   * 60 + end[1]
    if s < e:
        return s <= t < e
    # overnight session (e.g. 21:00 – 06:00)
    return t >= s or t < e


# ── data classes ──────────────────────────────────────────────────────────────

@dataclass
class BORLevels:
    s1: float = float("nan")
    s2: float = float("nan")
    s3: float = float("nan")
    s4: float = float("nan")

    @property
    def valid(self):
        return not any(math.isnan(v) for v in (self.s1, self.s2, self.s3, self.s4))


@dataclass
class Trade:
    symbol:      str
    session:     str           # "tokyo" | "london"
    direction:   str           # "buy"   | "sell"
    entry:       float
    sl:          float
    tp:          float
    lot_size:    float
    open_time:   datetime.datetime
    ticket:      int = 0

    closed:      bool  = False
    won:         Optional[bool] = None
    close_price: Optional[float] = None
    close_time:  Optional[datetime.datetime] = None
    wicked_out:  bool = False


@dataclass
class SessionState:
    name:        str
    start:       tuple
    end:         tuple
    levels:      BORLevels = field(default_factory=BORLevels)
    initialized: bool = False
    won:         bool = False
    trade_count: int  = 0

    def reset(self):
        self.levels      = BORLevels()
        self.initialized = False
        self.won         = False
        self.trade_count = 0


# ── main strategy engine ──────────────────────────────────────────────────────

class BORStrategy:
    """
    Stateful BOR strategy engine matching the LuxAlgo Pine Script exactly.

    Call on_candle() once per closed 15-min candle.
    Returns a list of signal dicts (may be empty).
    """

    def __init__(self, symbol: str, risk_pct: float, account_balance_fn,
                 max_trades: int = 2, tp_mult: float = 10.0,
                 tokyo_start=(0, 0),  tokyo_end=(9, 0),
                 london_start=(7, 0), london_end=(16, 0)):
        self.symbol      = symbol
        self.risk_pct    = risk_pct
        self.get_balance = account_balance_fn
        self.max_trades  = max_trades
        self.tp_mult     = tp_mult

        self.tokyo  = SessionState("tokyo",  tokyo_start,  tokyo_end)
        self.london = SessionState("london", london_start, london_end)

        # ── global trade slot (Pine: single tr_active across all sessions) ──
        self.active_trade: Optional[Trade] = None

        # ── global wick-out state (Pine: tr_wicked_out / tr_prev_entry / tr_prev_is_buy) ──
        self.wicked_out:      bool  = False
        self.prev_entry:      float = float("nan")
        self.prev_is_buy:     bool  = False

        # ── fixed risk: always use initial balance for risk calculation ──
        self.initial_balance = account_balance_fn()

        # stats
        self.wins         = 0
        self.losses       = 0
        self.pnl          = 0.0
        self.tokyo_wins   = 0
        self.tokyo_losses = 0
        self.london_wins  = 0
        self.london_losses = 0

    # ── public ────────────────────────────────────────────────────────────────

    def on_candle(self, utc_dt: datetime.datetime,
                  high: float, low: float, close: float, prev_close: float,
                  pre_h: float, pre_l: float,
                  open_h: float, open_l: float) -> list:
        """
        Process one closed 15-min candle.

        pre_h / pre_l   : high/low of the last CLOSED 15-min candle BEFORE session open
        open_h / open_l : high/low of the FIRST 15-min candle OF the session

        Returns list of signal dicts (empty if nothing triggered).
        """
        signals = []

        tky_in = in_session(utc_dt, self.tokyo.start,  self.tokyo.end)
        ldn_in = in_session(utc_dt, self.london.start, self.london.end)

        # ── PRIORITY LOGIC: London takes priority when both are active ──
        # When London starts, Tokyo levels become invalid immediately
        if ldn_in and tky_in:
            # Both active → London has priority, Tokyo levels are invalidated
            tky_in = False  # Treat Tokyo as inactive
            if self.tokyo.initialized:
                # Invalidate Tokyo levels when London starts
                self.tokyo.levels = BORLevels()  # Reset to invalid

        # ── detect session end and reset initialized flag ──────────────────
        if not tky_in and self.tokyo.initialized:
            self.tokyo.initialized = False
        if not ldn_in and self.london.initialized:
            self.london.initialized = False

        # ── session open: snapshot levels + reset session state ───────────
        # Pine resets tr_wicked_out on each session open
        if tky_in and not self.tokyo.initialized:
            self.tokyo.reset()
            s1, s2, s3, s4 = sort4(pre_h, pre_l, open_h, open_l)
            self.tokyo.levels     = BORLevels(s1, s2, s3, s4)
            self.tokyo.initialized = True
            self.wicked_out = False   # Pine: tr_wicked_out := false on session open

        if ldn_in and not self.london.initialized:
            self.london.reset()
            s1, s2, s3, s4 = sort4(pre_h, pre_l, open_h, open_l)
            self.london.levels     = BORLevels(s1, s2, s3, s4)
            self.london.initialized = True
            self.wicked_out = False   # Pine: tr_wicked_out := false on session open

        # ── check active trade outcome ────────────────────────────────────
        if self.active_trade and not self.active_trade.closed:
            t   = self.active_trade
            ses = self.tokyo if t.session == "tokyo" else self.london
            ses_still_active = tky_in if t.session == "tokyo" else ldn_in

            won  = (high >= t.tp) if t.direction == "buy" else (low  <= t.tp)
            lost = (low  <= t.sl) if t.direction == "buy" else (high >= t.sl)

            if won:
                self._close_trade(ses, t.tp, utc_dt, reason="tp")
            elif lost:
                # Wick-out: SL wick but body did NOT close beyond SL
                body_closed_out = (close < t.sl if t.direction == "buy"
                                   else close > t.sl)
                self.wicked_out  = not body_closed_out
                self.prev_entry  = t.entry
                self.prev_is_buy = (t.direction == "buy")
                self._close_trade(ses, t.sl, utc_dt, reason="sl")
            elif not ses_still_active:
                # Session ended with trade still open — close at market
                self._close_trade(ses, close, utc_dt, reason="session_end")

        # ── signal detection ──────────────────────────────────────────────
        # Pine: only one trade active globally
        if self.active_trade and not self.active_trade.closed:
            return signals

        # Global wick-out filter (Pine: _wko_buy_ok / _wko_sell_ok)
        wko_buy_ok  = (not (self.wicked_out and self.prev_is_buy)
                       or close > self.prev_entry)
        wko_sell_ok = (not (self.wicked_out and not self.prev_is_buy)
                       or close < self.prev_entry)

        for ses, ses_in in ((self.tokyo, tky_in), (self.london, ldn_in)):
            if not ses_in:
                continue
            lvl = ses.levels
            if not lvl.valid:
                continue
            if ses.won or ses.trade_count >= self.max_trades:
                continue

            # Breakout conditions — close crosses s1/s4 (Pine: close > tky_top / close < tky_bot)
            buy_signal  = (close > lvl.s1 and prev_close <= lvl.s1 and wko_buy_ok)
            sell_signal = (close < lvl.s4 and prev_close >= lvl.s4 and wko_sell_ok)

            if not (buy_signal or sell_signal):
                continue

            direction = "buy" if buy_signal else "sell"
            entry = lvl.s1 if buy_signal else lvl.s4
            sl    = lvl.s2 if buy_signal else lvl.s3
            tp    = (entry + abs(entry - sl) * self.tp_mult if buy_signal
                     else entry - abs(sl - entry) * self.tp_mult)

            lot = self._calc_lot(entry, sl)
            trade = Trade(
                symbol=self.symbol, session=ses.name,  # ← Trade belongs to session where it was OPENED
                direction=direction, entry=entry, sl=sl, tp=tp,
                lot_size=lot, open_time=utc_dt,
            )
            self.active_trade = trade
            ses.trade_count  += 1  # ← Increment count for the OPENING session

            signals.append({
                "symbol":    self.symbol,
                "session":   ses.name,  # ← Signal tagged with OPENING session
                "direction": direction,
                "entry":     entry,
                "sl":        sl,
                "tp":        tp,
                "lot_size":  lot,
                "time":      utc_dt,
            })
            break  # Pine: only one signal per candle (single global slot)

        return signals

    # ── private ───────────────────────────────────────────────────────────────

    def _close_trade(self, ses: SessionState, price: float,
                     utc_dt: datetime.datetime, reason: str):
        t = self.active_trade
        t.closed      = True
        t.close_price = price
        t.close_time  = utc_dt

        risk_dollar = self.initial_balance * self.risk_pct / 100.0
        is_tky      = (ses.name == "tokyo")

        if reason == "tp":
            t.won   = True
            ses.won = True
            pnl     = risk_dollar * self.tp_mult
            self.wins += 1
            self.pnl  += pnl
            if is_tky: self.tokyo_wins   += 1
            else:       self.london_wins  += 1

        elif reason == "sl":
            t.won        = False
            t.wicked_out = self.wicked_out
            pnl          = -risk_dollar
            self.losses += 1
            self.pnl    += pnl
            if is_tky: self.tokyo_losses  += 1
            else:       self.london_losses += 1

        else:  # session_end — flat at market
            sl_dist    = abs(t.entry - t.sl)
            price_dist = (price - t.entry if t.direction == "buy"
                          else t.entry - price)
            pnl = risk_dollar * (price_dist / sl_dist) if sl_dist else 0
            if pnl >= 0:
                self.wins += 1
                if is_tky: self.tokyo_wins   += 1
                else:       self.london_wins  += 1
            else:
                self.losses += 1
                if is_tky: self.tokyo_losses  += 1
                else:       self.london_losses += 1
            self.pnl += pnl

    def _calc_lot(self, entry: float, sl: float) -> float:
        risk_usd = self.initial_balance * self.risk_pct / 100.0
        sl_dist  = abs(entry - sl)
        if sl_dist == 0:
            return 0.01
        return risk_usd / sl_dist
