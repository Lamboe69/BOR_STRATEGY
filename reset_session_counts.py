"""
reset_session_counts.py - Utility to view and reset session trade counts

Use this if you need to manually reset trade counts for testing or after issues.
"""

import json
from pathlib import Path

DB_FILE = Path(__file__).parent / "bor_trades.db.json"

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text())
    return {"open_trades": {}, "closed_trades": [], "session_stats": {}, "version": "2.0"}

def save_db(data):
    DB_FILE.write_text(json.dumps(data, indent=2))

def view_counts():
    """Display current trade counts for all symbols"""
    data = load_db()
    stats = data.get("session_stats", {})
    
    if not stats:
        print("No session stats found in database.")
        return
    
    print("\n" + "="*60)
    print("CURRENT SESSION TRADE COUNTS")
    print("="*60)
    
    for symbol, sessions in stats.items():
        print(f"\n{symbol}:")
        for session, counts in sessions.items():
            trade_count = counts.get("trade_count", 0)
            wins = counts.get("wins", 0)
            losses = counts.get("losses", 0)
            print(f"  {session.upper():7} - Trades: {trade_count}/2  |  W/L: {wins}/{losses}")
    
    print("\n" + "="*60)

def reset_all_counts():
    """Reset all trade counts to 0 (keeps W/L stats)"""
    data = load_db()
    stats = data.get("session_stats", {})
    
    if not stats:
        print("No session stats to reset.")
        return
    
    for symbol in stats:
        for session in stats[symbol]:
            stats[symbol][session]["trade_count"] = 0
    
    save_db(data)
    print("\n✓ All trade counts reset to 0")
    print("  (Win/Loss stats preserved)")

def reset_symbol_counts(symbol):
    """Reset trade counts for a specific symbol"""
    data = load_db()
    stats = data.get("session_stats", {})
    
    if symbol not in stats:
        print(f"Symbol {symbol} not found in database.")
        return
    
    for session in stats[symbol]:
        stats[symbol][session]["trade_count"] = 0
    
    save_db(data)
    print(f"\n✓ Trade counts reset to 0 for {symbol}")
    print("  (Win/Loss stats preserved)")

def reset_session_counts(session_name):
    """Reset trade counts for a specific session (tokyo/london) across all symbols"""
    data = load_db()
    stats = data.get("session_stats", {})
    
    if not stats:
        print("No session stats to reset.")
        return
    
    session_name = session_name.lower()
    if session_name not in ["tokyo", "london"]:
        print("Session must be 'tokyo' or 'london'")
        return
    
    count = 0
    for symbol in stats:
        if session_name in stats[symbol]:
            stats[symbol][session_name]["trade_count"] = 0
            count += 1
    
    save_db(data)
    print(f"\n✓ {session_name.upper()} trade counts reset to 0 for {count} symbols")
    print("  (Win/Loss stats preserved)")

def main():
    print("\n" + "="*60)
    print("SESSION TRADE COUNT MANAGER")
    print("="*60)
    print("\nOptions:")
    print("  1. View current counts")
    print("  2. Reset ALL trade counts (all symbols, all sessions)")
    print("  3. Reset counts for specific symbol")
    print("  4. Reset counts for specific session (Tokyo/London)")
    print("  5. Exit")
    
    choice = input("\nEnter choice (1-5): ").strip()
    
    if choice == "1":
        view_counts()
    elif choice == "2":
        confirm = input("\nReset ALL trade counts? (yes/no): ").strip().lower()
        if confirm == "yes":
            reset_all_counts()
            view_counts()
    elif choice == "3":
        symbol = input("Enter symbol (e.g., XAUUSD): ").strip().upper()
        reset_symbol_counts(symbol)
        view_counts()
    elif choice == "4":
        session = input("Enter session (tokyo/london): ").strip().lower()
        reset_session_counts(session)
        view_counts()
    elif choice == "5":
        print("\nExiting...")
    else:
        print("\nInvalid choice.")

if __name__ == "__main__":
    main()
