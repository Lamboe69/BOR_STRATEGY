"""
performance_tracker.py — Track balance and equity history for performance graphs
"""

import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
PERF_FILE = ROOT / "performance_history.json"

def load_history():
    """Load performance history from file"""
    try:
        if PERF_FILE.exists():
            return json.loads(PERF_FILE.read_text())
        return {"history": [], "initial_balance": None, "start_time": None}
    except Exception:
        return {"history": [], "initial_balance": None, "start_time": None}

def save_snapshot(balance: float, equity: float):
    """Save a balance/equity snapshot"""
    data = load_history()
    
    # Set initial balance on first run
    if data["initial_balance"] is None:
        data["initial_balance"] = balance
        data["start_time"] = datetime.now(timezone.utc).isoformat()
    
    # Add new snapshot
    snapshot = {
        "time": datetime.now(timezone.utc).isoformat(),
        "balance": round(balance, 2),
        "equity": round(equity, 2)
    }
    
    data["history"].append(snapshot)
    
    # Keep ALL historical data (no limit) - compress old data by keeping every Nth point
    # Keep last 500 points at full resolution (1 second intervals)
    # For older data, keep every 10th point to save space while preserving the shape
    if len(data["history"]) > 1000:
        # Keep first point (start)
        compressed = [data["history"][0]]
        
        # Compress middle section (keep every 10th point)
        middle_section = data["history"][1:-500]
        compressed.extend([middle_section[i] for i in range(0, len(middle_section), 10)])
        
        # Keep last 500 points at full resolution
        compressed.extend(data["history"][-500:])
        
        data["history"] = compressed
    
    try:
        PERF_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass

def get_stats():
    """Calculate performance statistics"""
    data = load_history()
    
    if not data["history"] or data["initial_balance"] is None:
        return {
            "initial_balance": 0,
            "current_balance": 0,
            "current_equity": 0,
            "total_pnl": 0,
            "total_pnl_pct": 0,
            "peak_balance": 0,
            "drawdown": 0,
            "drawdown_pct": 0,
            "history": []
        }
    
    initial = data["initial_balance"]
    latest = data["history"][-1]
    current_balance = latest["balance"]
    current_equity = latest["equity"]
    
    # Find peak balance
    peak_balance = max(h["balance"] for h in data["history"])
    
    # Calculate drawdown from peak
    drawdown = peak_balance - current_balance
    drawdown_pct = (drawdown / peak_balance * 100) if peak_balance > 0 else 0
    
    # Total P&L
    total_pnl = current_balance - initial
    total_pnl_pct = (total_pnl / initial * 100) if initial > 0 else 0
    
    return {
        "initial_balance": round(initial, 2),
        "current_balance": round(current_balance, 2),
        "current_equity": round(current_equity, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "peak_balance": round(peak_balance, 2),
        "drawdown": round(drawdown, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "history": data["history"]  # Return ALL historical data points
    }
