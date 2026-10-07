"""Check the behavior_recordings table in the database."""
import sqlite3
from pathlib import Path

db_path = Path(__file__).parent / "logs" / "keylogger_events.db"

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# List all tables
print("=" * 60)
print("TABLES IN DATABASE:")
print("=" * 60)
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [row[0] for row in cursor.fetchall()]
for table in tables:
    print(f"  • {table}")

print()

# Check if behavior_recordings exists
if "behavior_recordings" in tables:
    print("=" * 60)
    print("BEHAVIOR_RECORDINGS TABLE:")
    print("=" * 60)
    
    # Count total rows
    cursor.execute("SELECT COUNT(*) FROM behavior_recordings")
    total = cursor.fetchone()[0]
    print(f"Total rows: {total}")
    
    if total > 0:
        # Show sessions
        cursor.execute("""
            SELECT session_id, COUNT(*) as count, 
                   MIN(recorded_at) as start, 
                   MAX(recorded_at) as end
            FROM behavior_recordings
            GROUP BY session_id
            ORDER BY MAX(recorded_at) DESC
        """)
        
        print("\nSessions:")
        for row in cursor.fetchall():
            session_id, count, start, end = row
            from datetime import datetime
            start_dt = datetime.fromtimestamp(start).strftime("%Y-%m-%d %H:%M:%S")
            end_dt = datetime.fromtimestamp(end).strftime("%Y-%m-%d %H:%M:%S")
            print(f"  Session: {session_id[:8]}...")
            print(f"    Samples: {count}")
            print(f"    Started: {start_dt}")
            print(f"    Ended:   {end_dt}")
            print()
    else:
        print("\n⚠️  No recordings found in the table.")
else:
    print("⚠️  behavior_recordings table does NOT exist!")

conn.close()
