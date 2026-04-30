"""
database_info.py - View database statistics and health information

Run this to see how much data is stored and database health.
"""

import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent
DB_FILE = ROOT / "bor_trades.db.json"
PERF_FILE = ROOT / "performance_history.json"

def format_size(bytes_size):
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def load_trades_db():
    """Load trades database"""
    try:
        if DB_FILE.exists():
            return json.loads(DB_FILE.read_text())
        return None
    except Exception as e:
        return None

def load_perf_db():
    """Load performance database"""
    try:
        if PERF_FILE.exists():
            return json.loads(PERF_FILE.read_text())
        return None
    except Exception as e:
        return None

def main():
    print("\n" + "="*70)
    print("BOR BOT - DATABASE HEALTH & STATISTICS")
    print("="*70)
    
    # Trades Database
    print("\n📊 TRADES DATABASE (bor_trades.db.json)")
    print("-" * 70)
    
    if DB_FILE.exists():
        db_size = DB_FILE.stat().st_size
        print(f"  File Size: {format_size(db_size)}")
        
        db = load_trades_db()
        if db:
            closed_trades = db.get("closed_trades", [])
            open_trades = db.get("open_trades", {})
            session_stats = db.get("session_stats", {})
            
            print(f"  Total Closed Trades: {len(closed_trades)}")
            print(f"  Currently Open Trades: {len(open_trades)}")
            print(f"  Symbols Tracked: {len(session_stats)}")
            print(f"  Database Version: {db.get('version', 'unknown')}")
            
            if closed_trades:
                print(f"\n  📈 Trade History:")
                oldest = closed_trades[0].get("time", "unknown")
                newest = closed_trades[-1].get("closed_at", "unknown")
                print(f"    Oldest Trade: {oldest}")
                print(f"    Newest Trade: {newest}")
                
                # Calculate total P&L
                total_pnl = sum(t.get("actual_pnl", 0) for t in closed_trades)
                wins = sum(1 for t in closed_trades if t.get("actual_pnl", 0) > 0)
                losses = sum(1 for t in closed_trades if t.get("actual_pnl", 0) < 0)
                total = wins + losses
                win_rate = (wins / total * 100) if total > 0 else 0
                
                print(f"\n  💰 All-Time Performance:")
                print(f"    Total P&L: ${total_pnl:,.2f}")
                print(f"    Wins: {wins} | Losses: {losses}")
                print(f"    Win Rate: {win_rate:.1f}%")
            
            if session_stats:
                print(f"\n  📊 Per-Symbol Statistics:")
                for symbol, stats in session_stats.items():
                    tokyo = stats.get("tokyo", {})
                    london = stats.get("london", {})
                    
                    tokyo_total = tokyo.get("wins", 0) + tokyo.get("losses", 0)
                    london_total = london.get("wins", 0) + london.get("losses", 0)
                    
                    tokyo_wr = (tokyo.get("wins", 0) / tokyo_total * 100) if tokyo_total > 0 else 0
                    london_wr = (london.get("wins", 0) / london_total * 100) if london_total > 0 else 0
                    
                    print(f"\n    {symbol}:")
                    print(f"      Tokyo:  {tokyo.get('wins', 0)}W/{tokyo.get('losses', 0)}L ({tokyo_wr:.1f}% WR)")
                    print(f"      London: {london.get('wins', 0)}W/{london.get('losses', 0)}L ({london_wr:.1f}% WR)")
        else:
            print("  ⚠️  Could not read database (corrupted?)")
    else:
        print("  ❌ Database file not found")
    
    # Performance Database
    print("\n\n📈 PERFORMANCE DATABASE (performance_history.json)")
    print("-" * 70)
    
    if PERF_FILE.exists():
        perf_size = PERF_FILE.stat().st_size
        print(f"  File Size: {format_size(perf_size)}")
        
        perf = load_perf_db()
        if perf:
            history = perf.get("history", [])
            initial = perf.get("initial_balance")
            start_time = perf.get("start_time")
            
            print(f"  Data Points: {len(history)}")
            print(f"  Initial Balance: ${initial:,.2f}" if initial else "  Initial Balance: Not set")
            print(f"  Start Time: {start_time}" if start_time else "  Start Time: Not set")
            
            if history:
                latest = history[-1]
                current_balance = latest.get("balance", 0)
                current_equity = latest.get("equity", 0)
                
                if initial:
                    pnl = current_balance - initial
                    pnl_pct = (pnl / initial * 100)
                    
                    print(f"\n  💰 Current Status:")
                    print(f"    Balance: ${current_balance:,.2f}")
                    print(f"    Equity: ${current_equity:,.2f}")
                    print(f"    Total P&L: ${pnl:,.2f} ({pnl_pct:+.2f}%)")
                    
                    # Peak and drawdown
                    peak = max(h.get("balance", 0) for h in history)
                    dd = peak - current_balance
                    dd_pct = (dd / peak * 100) if peak > 0 else 0
                    
                    print(f"\n  📊 Drawdown:")
                    print(f"    Peak Balance: ${peak:,.2f}")
                    print(f"    Current Drawdown: ${dd:,.2f} ({dd_pct:.2f}%)")
        else:
            print("  ⚠️  Could not read database (corrupted?)")
    else:
        print("  ❌ Database file not found")
    
    # Recommendations
    print("\n\n💡 RECOMMENDATIONS")
    print("-" * 70)
    
    if DB_FILE.exists():
        db_size = DB_FILE.stat().st_size
        if db_size > 10 * 1024 * 1024:  # > 10 MB
            print("  ⚠️  Database is large (>10MB). Consider backing up regularly.")
        else:
            print("  ✅ Database size is healthy.")
    
    if DB_FILE.exists() and PERF_FILE.exists():
        print("  ✅ All databases present and accessible.")
        print("\n  📁 Backup these files regularly:")
        print(f"     - {DB_FILE}")
        print(f"     - {PERF_FILE}")
        print(f"     - {ROOT / 'bor_settings.json'}")
    else:
        print("  ⚠️  Some database files are missing.")
    
    print("\n" + "="*70)
    print()

if __name__ == "__main__":
    main()
