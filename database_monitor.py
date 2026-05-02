"""
database_monitor.py - Monitor and verify BOR Bot database health
"""

import json
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).parent / "bor_trades.db.json"

def load_database():
    """Load database from file"""
    if not DB_PATH.exists():
        print("❌ Database file not found!")
        return None
    
    try:
        return json.loads(DB_PATH.read_text())
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        return None

def format_size(bytes):
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024
    return f"{bytes:.2f} TB"

def analyze_database():
    """Analyze and display database statistics"""
    data = load_database()
    if not data:
        return
    
    print("\n" + "="*60)
    print("BOR BOT - DATABASE HEALTH REPORT")
    print("="*60)
    
    # Basic Info
    print("\n[DATABASE OVERVIEW]")
    print("-" * 60)
    file_size = DB_PATH.stat().st_size
    print(f"File: {DB_PATH.name}")
    print(f"Size: {format_size(file_size)}")
    print(f"Version: {data.get('version', 'unknown')}")
    print(f"Last Modified: {datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Open Trades
    open_trades = data.get("open_trades", {})
    print(f"\n[OPEN TRADES]: {len(open_trades)}")
    print("-" * 60)
    if open_trades:
        for ticket, trade in open_trades.items():
            symbol = trade.get('symbol', 'Unknown')
            direction = trade.get('direction', '?').upper()
            session = trade.get('session', '?').upper()
            pnl = trade.get('pnl', 0)
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            print(f"  #{ticket}: {symbol} {direction} ({session}) - P&L: {pnl_str}")
    else:
        print("  No open trades")
    
    # Closed Trades
    closed_trades = data.get("closed_trades", [])
    print(f"\n[CLOSED TRADES]: {len(closed_trades)} (PERMANENT)")
    print("-" * 60)
    
    if closed_trades:
        # Calculate statistics
        total_pnl = sum(t.get('actual_pnl', 0) for t in closed_trades)
        wins = [t for t in closed_trades if t.get('close_reason') == 'tp']
        losses = [t for t in closed_trades if t.get('close_reason') == 'sl']
        win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
        
        print(f"  Total P&L: ${total_pnl:.2f}")
        print(f"  Wins: {len(wins)} | Losses: {len(losses)}")
        print(f"  Win Rate: {win_rate:.1f}%")
        
        # Recent trades
        print(f"\n  Recent Trades (Last 5):")
        for trade in closed_trades[-5:]:
            ticket = trade.get('ticket', '?')
            symbol = trade.get('symbol', '?')
            direction = trade.get('direction', '?').upper()
            reason = trade.get('close_reason', '?').upper()
            pnl = trade.get('actual_pnl', 0)
            pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
            result = "[WIN]" if reason == "TP" else "[LOSS]" if reason == "SL" else "[CLOSED]"
            print(f"    {result} #{ticket}: {symbol} {direction} - {reason} - {pnl_str}")
    else:
        print("  No closed trades yet")
    
    # Session Statistics
    session_stats = data.get("session_stats", {})
    print(f"\n[SESSION STATISTICS]")
    print("-" * 60)
    
    if session_stats:
        for symbol, sessions in session_stats.items():
            print(f"\n  {symbol}:")
            for session_name, stats in sessions.items():
                wins = stats.get('wins', 0)
                losses = stats.get('losses', 0)
                trade_count = stats.get('trade_count', 0)
                total = wins + losses
                wr = (wins / total * 100) if total > 0 else 0
                print(f"    {session_name.upper()}: {wins}W/{losses}L (WR: {wr:.1f}%) | Current: {trade_count}/2 trades")
    else:
        print("  No session statistics yet")
    
    # Data Integrity
    print(f"\n[DATA INTEGRITY]")
    print("-" * 60)
    
    # Check for required fields in closed trades
    required_fields = ['ticket', 'symbol', 'direction', 'session', 'entry', 'sl', 'tp']
    issues = 0
    
    for i, trade in enumerate(closed_trades):
        missing = [f for f in required_fields if f not in trade]
        if missing:
            print(f"  ⚠️ Trade {i}: Missing fields {missing}")
            issues += 1
    
    if issues == 0:
        print("  [OK] All trades have required fields")
    else:
        print(f"  [WARNING] Found {issues} trades with missing fields")
    
    # Storage Estimates
    print(f"\n[STORAGE ESTIMATES]")
    print("-" * 60)
    avg_trade_size = file_size / len(closed_trades) if closed_trades else 500
    print(f"  Average trade size: {format_size(avg_trade_size)}")
    print(f"  Estimated at 1,000 trades: {format_size(avg_trade_size * 1000)}")
    print(f"  Estimated at 10,000 trades: {format_size(avg_trade_size * 10000)}")
    
    # Backup Recommendation
    print(f"\n[RECOMMENDATIONS]")
    print("-" * 60)
    
    if len(closed_trades) > 100:
        print("  [OK] Consider backing up database (100+ trades)")
    
    if file_size > 1024 * 1024:  # > 1 MB
        print("  [INFO] Database size > 1 MB - consider archiving old trades")
    
    if len(open_trades) > 10:
        print("  [WARNING] Many open trades - verify bot is running correctly")
    
    print("\n" + "="*60)
    print("[OK] DATABASE HEALTH CHECK COMPLETE")
    print("="*60 + "\n")

def backup_database():
    """Create a backup of the database"""
    if not DB_PATH.exists():
        print("❌ Database file not found!")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"bor_trades.db.backup_{timestamp}.json"
    
    try:
        backup_path.write_text(DB_PATH.read_text())
        print(f"[OK] Backup created: {backup_path.name}")
        print(f"   Size: {format_size(backup_path.stat().st_size)}")
    except Exception as e:
        print(f"[ERROR] Backup failed: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--backup":
        backup_database()
    else:
        analyze_database()
        
        print("\nOptions:")
        print("  python database_monitor.py          - Show this report")
        print("  python database_monitor.py --backup - Create backup")
