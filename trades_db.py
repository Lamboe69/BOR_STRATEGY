"""
trades_db.py — Persistent trade tracking database using JSON
Stores all trades so they survive bot restarts
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import datetime

class TradesDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.data = self._load()
    
    def _load(self) -> dict:
        """Load database from file"""
        if self.db_path.exists():
            try:
                return json.loads(self.db_path.read_text())
            except Exception:
                return {
                    "open_trades": {}, 
                    "closed_trades": [], 
                    "session_stats": {},  # Per-symbol: {"EURUSDm": {"tokyo": {"wins": 0, "losses": 0}, "london": {...}}}
                    "version": "2.0"
                }
        return {
            "open_trades": {}, 
            "closed_trades": [], 
            "session_stats": {},
            "version": "2.0"
        }
    
    def _save(self):
        """Save database to file"""
        try:
            self.db_path.write_text(json.dumps(self.data, indent=2))
        except Exception as e:
            print(f"Error saving trades DB: {e}")
    
    def add_open_trade(self, ticket: int, trade_data: dict):
        """Add or update an open trade"""
        self.data["open_trades"][str(ticket)] = {
            **trade_data,
            "last_updated": datetime.datetime.utcnow().isoformat()
        }
        self._save()
    
    def get_open_trade(self, ticket: int) -> Optional[dict]:
        """Get an open trade by ticket"""
        return self.data["open_trades"].get(str(ticket))
    
    def get_all_open_trades(self) -> Dict[int, dict]:
        """Get all open trades"""
        return {int(k): v for k, v in self.data["open_trades"].items()}
    
    def close_trade(self, ticket: int, close_data: dict):
        """Move trade from open to closed and update per-symbol session stats"""
        ticket_str = str(ticket)
        if ticket_str in self.data["open_trades"]:
            trade = self.data["open_trades"].pop(ticket_str)
            trade.update(close_data)
            trade["closed_at"] = datetime.datetime.utcnow().isoformat()
            self.data["closed_trades"].append(trade)
            
            # Update per-symbol session stats
            symbol = trade.get("symbol", "")
            session = trade.get("session", "manual")
            close_reason = close_data.get("close_reason", "closed")
            
            if symbol and session in ["tokyo", "london"]:
                if "session_stats" not in self.data:
                    self.data["session_stats"] = {}
                
                if symbol not in self.data["session_stats"]:
                    self.data["session_stats"][symbol] = {"tokyo": {"wins": 0, "losses": 0, "trade_count": 0}, "london": {"wins": 0, "losses": 0, "trade_count": 0}}
                
                if session not in self.data["session_stats"][symbol]:
                    self.data["session_stats"][symbol][session] = {"wins": 0, "losses": 0, "trade_count": 0}
                
                if close_reason == "tp":
                    self.data["session_stats"][symbol][session]["wins"] = self.data["session_stats"][symbol][session].get("wins", 0) + 1
                elif close_reason == "sl":
                    self.data["session_stats"][symbol][session]["losses"] = self.data["session_stats"][symbol][session].get("losses", 0) + 1
            
            # Store ALL closed trades permanently (no limit)
            # Historical data is critical for performance analysis
            
            self._save()
            return trade
        return None
    
    def get_closed_trades(self, limit: int = None) -> List[dict]:
        """Get closed trades (all if limit=None, or last N if limit specified)"""
        if limit is None:
            return self.data["closed_trades"]
        return self.data["closed_trades"][-limit:]
    
    def update_trade_pnl(self, ticket: int, pnl: float, current_price: float):
        """Update P&L for an open trade"""
        ticket_str = str(ticket)
        if ticket_str in self.data["open_trades"]:
            self.data["open_trades"][ticket_str]["pnl"] = pnl
            self.data["open_trades"][ticket_str]["current_price"] = current_price
            self.data["open_trades"][ticket_str]["last_updated"] = datetime.datetime.utcnow().isoformat()
            # Don't save on every update to avoid excessive I/O
            # Will be saved when trade closes or new trade opens
    
    def sync_with_mt5(self, mt5_tickets: set):
        """Remove trades that no longer exist in MT5"""
        removed = []
        for ticket_str in list(self.data["open_trades"].keys()):
            ticket = int(ticket_str)
            if ticket not in mt5_tickets:
                # Trade closed in MT5 but we didn't catch it
                trade = self.data["open_trades"].pop(ticket_str)
                trade["closed_at"] = datetime.datetime.utcnow().isoformat()
                trade["close_reason"] = "closed_by_broker"
                self.data["closed_trades"].append(trade)
                removed.append(ticket)
        
        if removed:
            self._save()
        
        return removed
    
    def get_session_stats(self, symbol: str = None) -> dict:
        """Get session statistics from database (per-symbol or all)"""
        if "session_stats" not in self.data:
            self.data["session_stats"] = {}
        
        if symbol:
            # Return stats for specific symbol
            if symbol not in self.data["session_stats"]:
                return {"tokyo": {"wins": 0, "losses": 0, "trade_count": 0}, "london": {"wins": 0, "losses": 0, "trade_count": 0}}
            return self.data["session_stats"][symbol]
        else:
            # Return all symbols
            return self.data["session_stats"]
    
    def increment_trade_count(self, symbol: str, session: str):
        """Increment trade count for a symbol's session"""
        if "session_stats" not in self.data:
            self.data["session_stats"] = {}
        
        if symbol not in self.data["session_stats"]:
            self.data["session_stats"][symbol] = {"tokyo": {"wins": 0, "losses": 0, "trade_count": 0}, "london": {"wins": 0, "losses": 0, "trade_count": 0}}
        
        if session not in self.data["session_stats"][symbol]:
            self.data["session_stats"][symbol][session] = {"wins": 0, "losses": 0, "trade_count": 0}
        
        self.data["session_stats"][symbol][session]["trade_count"] = self.data["session_stats"][symbol][session].get("trade_count", 0) + 1
        self._save()
    
    def decrement_trade_count(self, symbol: str, session: str):
        """Decrement trade count when a pending order is cancelled before filling"""
        if "session_stats" not in self.data:
            return
        
        if symbol not in self.data["session_stats"]:
            return
        
        if session not in self.data["session_stats"][symbol]:
            return
        
        current = self.data["session_stats"][symbol][session].get("trade_count", 0)
        if current > 0:
            self.data["session_stats"][symbol][session]["trade_count"] = current - 1
            self._save()
    
    def reset_session_counts(self, symbol: str, session: str):
        """Reset trade count for a symbol's session when new session starts"""
        if "session_stats" not in self.data:
            self.data["session_stats"] = {}
        
        if symbol not in self.data["session_stats"]:
            self.data["session_stats"][symbol] = {"tokyo": {"wins": 0, "losses": 0, "trade_count": 0}, "london": {"wins": 0, "losses": 0, "trade_count": 0}}
        
        if session in self.data["session_stats"][symbol]:
            self.data["session_stats"][symbol][session]["trade_count"] = 0
            self._save()
    
    def get_trade_count(self, symbol: str, session: str) -> int:
        """Get current trade count for a symbol's session"""
        if "session_stats" not in self.data:
            return 0
        
        if symbol not in self.data["session_stats"]:
            return 0
        
        if session not in self.data["session_stats"][symbol]:
            return 0
        
        return self.data["session_stats"][symbol][session].get("trade_count", 0)
    
    def get_all_time_stats(self, symbol: str = None) -> dict:
        """Get all-time statistics from ALL closed trades (permanent historical data)"""
        closed = self.data.get("closed_trades", [])
        
        if symbol:
            closed = [t for t in closed if t.get("symbol") == symbol]
        
        if not closed:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0,
                "total_pnl": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "avg_win": 0,
                "avg_loss": 0,
            }
        
        wins = []
        losses = []
        total_pnl = 0
        
        for trade in closed:
            pnl = trade.get("actual_pnl", 0)
            total_pnl += pnl
            
            if pnl > 0:
                wins.append(pnl)
            elif pnl < 0:
                losses.append(pnl)
        
        total_trades = len(wins) + len(losses)
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0
        
        return {
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
            "best_trade": round(max(wins) if wins else 0, 2),
            "worst_trade": round(min(losses) if losses else 0, 2),
            "avg_win": round(sum(wins) / len(wins) if wins else 0, 2),
            "avg_loss": round(sum(losses) / len(losses) if losses else 0, 2),
        }
    
    def get_database_info(self) -> dict:
        """Get information about the database (for monitoring)"""
        return {
            "total_closed_trades": len(self.data.get("closed_trades", [])),
            "open_trades": len(self.data.get("open_trades", {})),
            "symbols_tracked": list(self.data.get("session_stats", {}).keys()),
            "database_version": self.data.get("version", "unknown"),
            "database_size_kb": round(len(json.dumps(self.data)) / 1024, 2),
        }
    
    def clear_all(self):
        """Clear all data (use with caution)"""
        self.data = {
            "open_trades": {}, 
            "closed_trades": [], 
            "session_stats": {},
            "version": "2.0"
        }
        self._save()
